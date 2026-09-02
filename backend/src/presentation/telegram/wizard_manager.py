"""Telegram interactive account credential setup wizard manager."""

import logging
from typing import Any, Dict, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.bot.save_credentials_use_case import SaveCredentialsUseCase
from src.infrastructure.di.container import container
from src.presentation.api.schemas.system import TradingCredentialCreateRequest

logger = logging.getLogger(__name__)


class WizardStateDict(dict):
    """Dictionary supporting transparent lookup by either int or string chat_id."""

    def __contains__(self, key: Any) -> bool:
        return (
            super().__contains__(key)
            or super().__contains__(str(key))
            or (isinstance(key, str) and key.isdigit() and super().__contains__(int(key)))
        )

    def __getitem__(self, key: Any) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        if super().__contains__(str(key)):
            return super().__getitem__(str(key))
        if isinstance(key, str) and key.isdigit() and super().__contains__(int(key)):
            return super().__getitem__(int(key))
        return super().__getitem__(key)

    def pop(self, key: Any, default: Any = None) -> Any:
        if super().__contains__(key):
            return super().pop(key, default)
        if super().__contains__(str(key)):
            return super().pop(str(key), default)
        if isinstance(key, str) and key.isdigit() and super().__contains__(int(key)):
            return super().pop(int(key), default)
        return default


# Shared in-memory wizard state across chat sessions
wizard_states = WizardStateDict()


class TelegramWizardManager:
    """Manages the multi-step interactive account setup wizard."""

    def __init__(
        self,
        session: AsyncSession,
        save_credentials_use_case: Optional[SaveCredentialsUseCase] = None,
        notification_gateway: Optional[Any] = None,
    ) -> None:
        self.session = session
        self._save_credentials_use_case = save_credentials_use_case
        self.notification_gateway = notification_gateway or getattr(container, "notification_gateway", None)

    @property
    def save_credentials_use_case(self) -> SaveCredentialsUseCase:
        return self._save_credentials_use_case or container.get_save_credentials_use_case(self.session)


    def is_in_wizard(self, chat_id: Union[int, str]) -> bool:
        """Check if the given chat is currently in a setup wizard flow."""
        return chat_id in wizard_states

    def cancel_wizard(self, chat_id: Union[int, str]) -> str:
        """Cancel an ongoing wizard session."""
        wizard_states.pop(chat_id, None)
        return "❌ Setup akun dibatalkan."

    async def start_wizard(self, chat_id: Union[int, str]) -> Dict[str, Any]:
        """Start the interactive account credential setup wizard."""
        wizard_states[chat_id] = {"step": "SELECT_ENV"}
        keyboard = [
            [
                {"text": "🧪 TESTNET (Demo)", "callback_data": "wizard_env_testnet"},
                {"text": "⚡ MAINNET (Live)", "callback_data": "wizard_env_mainnet"},
            ],
            [{"text": "❌ Batal", "callback_data": "wizard_cancel"}],
        ]
        return {
            "text": (
                "🔐 <b>WIZARD SETUP AKUN & KREDENSIAL BINANCE (SETUP KREDENSIAL BINANCE)</b>\n\n"
                "Pilih tipe lingkungan trading yang ingin Anda hubungkan:\n\n"
                "• <b>TESTNET</b>: Lingkungan simulasi / demo bebas risiko.\n"
                "• <b>MAINNET</b>: Akun riil Binance Futures dengan dana nyata."
            ),
            "reply_markup": {"inline_keyboard": keyboard},
        }

    async def handle_callback(self, chat_id: Union[int, str], data: str) -> Optional[Dict[str, Any]]:
        """Handle inline button callback within the setup wizard."""
        data_lower = data.lower()
        if data_lower in ("wizard_cancel", "wiz_cancel"):
            wizard_states.pop(chat_id, None)
            return {"status": "WIZARD_CANCELLED", "text": "❌ Setup akun dibatalkan."}

        if data_lower in ("wizard_env_testnet", "wiz_env_testnet", "wizard_env_mainnet", "wiz_env_mainnet"):
            env = "TESTNET" if "testnet" in data_lower else "MAINNET"
            wizard_states[chat_id] = {"step": "AWAITING_API_KEY", "env": env}
            return {
                "status": "WIZARD_STARTED",
                "env": env,
                "text": (
                    f"✅ Lingkungan: <b>{env}</b>\n\n"
                    "Silakan kirimkan <b>Binance API Key</b> Anda:\n"
                    "<i>(Pesan Anda akan otomatis diproses dan aman).</i>\n\n"
                    "Ketik /cancel kapan saja untuk membatalkan."
                ),
            }

        state = wizard_states.get(chat_id)
        if not state:
            return None
        return None

    async def handle_text_step(
        self,
        chat_id: Union[int, str],
        text: str,
        message_id: Optional[int] = None,
        account_id: Optional[int] = None,
        telegram_client: Optional[Any] = None,
        notification_gateway: Optional[Any] = None,
    ) -> Optional[str]:
        """Handle conversational text message during active wizard state."""
        state = wizard_states.get(chat_id)
        if not state:
            return None

        clean_text = text.strip()
        if clean_text.lower() == "/cancel":
            wizard_states.pop(chat_id, None)
            return "❌ Setup akun dibatalkan."

        step = state.get("step")
        del_client = telegram_client or notification_gateway or self.notification_gateway or getattr(container, "notification_gateway", None)

        # Step 1: Received API Key
        if step == "AWAITING_API_KEY":
            wizard_states[chat_id]["api_key"] = clean_text
            wizard_states[chat_id]["step"] = "AWAITING_API_SECRET"

            if del_client and message_id and hasattr(del_client, "delete_message"):
                try:
                    await del_client.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:
                    pass

            return (
                "✅ <b>API Key Diterima!</b> (API Key diterima)\n\n"
                "Sekarang kirimkan <b>Binance SECRET Key</b> Anda:\n"
                "<i>(Pesan berisi secret key akan otomatis dihapus demi keamanan).</i>"
            )

        # Step 2: Received API Secret -> Test Handshake & Save via Use Case
        elif step in ("AWAITING_SECRET_KEY", "AWAITING_API_SECRET"):
            api_key = state.get("api_key")
            api_secret = clean_text
            env = state.get("env", "TESTNET")

            wizard_states.pop(chat_id, None)

            if del_client and message_id and hasattr(del_client, "delete_message"):
                try:
                    await del_client.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception:
                    pass

            try:
                request_dto = TradingCredentialCreateRequest(
                    environment=env,
                    api_key=api_key,
                    secret_key=api_secret,
                    account_id=account_id,
                )
                save_resp = await self.save_credentials_use_case.execute(request_dto)
                masked_key = f"{api_key[:4]}****{api_key[-4:]}" if len(api_key) >= 8 else "apiK****"
                total_bal = save_resp.wallet_balance_usdt

                return (
                    f"🎉 <b>AKUN BINANCE BERHASIL DIHUBUNGKAN!</b>\n\n"
                    f"• <b>Lingkungan:</b> {env}\n"
                    f"• <b>API Key:</b> <code>{masked_key}</code>\n"
                    f"• <b>Saldo Terbaca:</b> <b>${float(total_bal):,.2f} USDT</b>\n"
                    f"• <b>Status:</b> <b>CONNECTED & READY ✅</b>\n\n"
                    "Bot trading siap menerima dan mengeksekusi sinyal."
                )
            except Exception as exc:
                logger.warning("Binance credential handshake failed: %s", exc)
                return (
                    f"❌ <b>Verifikasi Binance Gagal</b>\n\n"
                    f"Kredensial API tidak valid atau gagal terhubung ke Binance {env}.\n"
                    f"<b>Error:</b> {exc}\n\n"
                    "Silakan ulangi kembali dengan perintah /setup_account."
                )

        return None
