from decimal import Decimal
import asyncio
import logging
from typing import Any, Dict, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto.signal_commands import ApproveSignalCommand, ParseSignalCommand, RejectSignalCommand
from src.infrastructure.di.container import container
from src.presentation.telegram.wizard_manager import TelegramWizardManager
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.presentation.api.schemas.master import SignalProviderCreate

logger = logging.getLogger(__name__)


class TelegramBotController:
    """Entry controller for handling incoming Telegram messages, commands, and inline callbacks."""

    def __init__(
        self,
        session: AsyncSession,
        notification_gateway: Optional[Any] = None,
        wizard_manager: Optional[TelegramWizardManager] = None,
        command_use_case: Optional[Any] = None,
    ) -> None:
        self.session = session
        self.notification_gateway = notification_gateway or getattr(container, "notification_gateway", None)
        self.wizard_manager = wizard_manager or TelegramWizardManager(session)
        self.command_use_case = command_use_case or container.get_handle_command_use_case(session)
        self.parse_signal_use_case = container.get_parse_signal_use_case(session)
        self.approve_signal_use_case = container.get_approve_signal_use_case(session)
        self.reject_signal_use_case = container.get_reject_signal_use_case(session)
        self.provider_repo = SignalProviderRepository(session)

    async def handle_user_message(
        self,
        raw_text: str,
        chat_id: Union[int, str],
        message_id: Optional[int] = None,
        account_id: int = 1,
    ) -> Optional[str]:
        """Route incoming user text to setup wizard, slash command dispatcher, or signal parser."""
        clean_text = raw_text.strip()
        if not clean_text:
            return None

        # 1. Handle Active Wizard Session
        if self.wizard_manager.is_in_wizard(chat_id):
            return await self.wizard_manager.handle_text_step(
                chat_id=chat_id,
                text=clean_text,
                message_id=message_id,
                account_id=account_id,
            )

        # 2. Setup Account Wizard command initiation
        if clean_text.lower().startswith(("/setup_account", "/account_setup", "/set_credentials")):
            wizard_resp = await self.wizard_manager.start_wizard(chat_id)

            if self.notification_gateway and hasattr(self.notification_gateway, "send_message"):
                try:
                    await self.notification_gateway.send_message(
                        chat_id=chat_id,
                        text=wizard_resp["text"],
                        reply_markup=wizard_resp.get("reply_markup"),
                    )
                except Exception as exc:
                    logger.debug("Could not send Telegram message via gateway: %s", exc)
            return wizard_resp.get("text")

        # 3. Handle Other Slash Commands
        if clean_text.startswith("/"):
            return await self.command_use_case.execute(
                command=clean_text,
                chat_id=chat_id,
            )

        # 4. Handle Potential Trading Signal Text
        try:
            # Auto-resolve default Telegram signal provider
            provider = await self.provider_repo.get_by_name("Telegram Manual Channel")
            if not provider:
                provider = await self.provider_repo.create(
                    SignalProviderCreate(
                        name="Telegram Manual Channel",
                        type="TELEGRAM",
                        is_active=True,
                    )
                )

            parse_cmd = ParseSignalCommand(
                raw_text=clean_text,
                provider_id=provider.id,
                channel_id=f"Telegram Chat #{chat_id}",
            )
            signal_dto = await self.parse_signal_use_case.execute(parse_cmd)

            # Send interactive confirmation card
            if self.notification_gateway and hasattr(self.notification_gateway, "send_signal_confirmation"):
                entry_range_str = (
                    f"{signal_dto.entry_min} - {signal_dto.entry_max}"
                    if (signal_dto.entry_min and signal_dto.entry_max)
                    else str(signal_dto.avg_entry_price)
                )
                try:
                    await self.notification_gateway.send_signal_confirmation(
                        chat_id=chat_id,
                        signal_id=signal_dto.id,
                        symbol=signal_dto.symbol,
                        side=signal_dto.side,
                        entry_range=entry_range_str,
                        sl=signal_dto.sl_price,
                        tp_targets=signal_dto.tp_targets or [],
                        confidence=Decimal(str(signal_dto.confidence_score)),
                    )
                except Exception as exc:
                    logger.debug("Could not send signal confirmation card: %s", exc)
            return None
        except Exception as exc:
            logger.debug("Text is not a recognizable trade signal: %s", exc)
            return None

    async def handle_callback_query(
        self,
        callback_data: str,
        message_id: Optional[int] = None,
        chat_id: Optional[Union[int, str]] = None,
    ) -> Optional[str]:
        """Dispatch inline button callbacks (Approval, Rejection, Setup Wizard)."""
        clean_cb = callback_data.strip()

        # 1. Wizard Callback
        if clean_cb.startswith(("wizard_", "WIZ_")):
            if chat_id:
                wizard_resp = await self.wizard_manager.handle_callback(chat_id, clean_cb)
                if wizard_resp and self.notification_gateway and hasattr(self.notification_gateway, "edit_message_text") and message_id:
                    try:
                        await self.notification_gateway.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=wizard_resp["text"],
                            reply_markup=wizard_resp.get("reply_markup"),
                        )
                    except Exception as exc:
                        logger.debug("Could not edit Telegram message: %s", exc)
                return wizard_resp.get("status") if wizard_resp else None
            return None

        # 2. Approve Signal Callback
        if clean_cb.startswith(("approve_signal:", "sig_app_", "APPROVE_")):
            try:
                sig_id = int(clean_cb.split(":")[-1] if ":" in clean_cb else clean_cb.split("_")[-1])
                approve_cmd = ApproveSignalCommand(signal_id=sig_id)
                res = await self.approve_signal_use_case.execute(approve_cmd)
                status_text = "✅ <b>SIGNAL APPROVED & EXECUTING</b>" if res.status in ("EXECUTED", "APPROVED") else f"⚠️ {res.message or 'Failed'}"
                if chat_id and message_id and self.notification_gateway and hasattr(self.notification_gateway, "edit_message_text"):
                    try:
                        await self.notification_gateway.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"{status_text}\n\nSignal #{sig_id} telah disetujui untuk dieksekusi.",
                        )
                    except Exception as exc:
                        logger.debug("Could not edit message on approve: %s", exc)
                return status_text
            except Exception as exc:
                logger.error("Error approving signal via callback: %s", exc)
                return f"❌ Gagal menyetujui sinyal: {exc}"

        # 3. Reject Signal Callback
        if clean_cb.startswith(("reject_signal:", "sig_rej_", "REJECT_")):
            try:
                sig_id = int(clean_cb.split(":")[-1] if ":" in clean_cb else clean_cb.split("_")[-1])
                reject_cmd = RejectSignalCommand(signal_id=sig_id, reason="REJECTED_BY_OPERATOR")
                reject_res = await self.reject_signal_use_case.execute(reject_cmd)
                if chat_id and message_id and self.notification_gateway and hasattr(self.notification_gateway, "edit_message_text"):
                    try:
                        await self.notification_gateway.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"❌ <b>SIGNAL REJECTED</b>\n\nSignal #{sig_id} telah ditolak.",
                        )
                    except Exception as exc:
                        logger.debug("Could not edit message on reject: %s", exc)
                return "❌ Signal rejected."
            except Exception as exc:
                logger.error("Error rejecting signal via callback: %s", exc)
                return f"❌ Gagal menolak sinyal: {exc}"



        return None

    @classmethod
    def start_polling_task(cls) -> Optional[asyncio.Task]:
        """Start the background Telegram polling runner."""
        if not (hasattr(container, "telegram_connector") and container.telegram_connector.bot_token):
            return None

        async def on_tg_message(msg: dict) -> None:
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id", 1)
            message_id = msg.get("message_id")
            if not text:
                return

            async with container.session_scope() as tg_session:
                ctrl = cls(session=tg_session)
                reply = await ctrl.handle_user_message(raw_text=text, chat_id=chat_id, message_id=message_id)
                if reply and isinstance(reply, str) and container.notification_gateway:
                    try:
                        await container.notification_gateway.send_message(chat_id=chat_id, text=reply)
                    except Exception as e:
                        logger.error("Error sending Telegram reply: %s", e)

        async def on_tg_callback(cq: dict) -> None:
            callback_data = cq.get("data", "")
            cq_id = cq.get("id")
            msg = cq.get("message", {})
            chat_id = msg.get("chat", {}).get("id", 1)
            message_id = msg.get("message_id")

            if cq_id and container.notification_gateway:
                try:
                    await container.notification_gateway.answer_callback_query(callback_query_id=cq_id)
                except Exception:
                    pass

            async with container.session_scope() as tg_session:
                ctrl = cls(session=tg_session)
                await ctrl.handle_callback_query(
                    callback_data=callback_data,
                    message_id=message_id,
                    chat_id=chat_id,
                )

        return asyncio.create_task(
            container.telegram_connector.start_polling(
                on_message_coro=on_tg_message,
                on_callback_query_coro=on_tg_callback,
            )
        )
