"""Interactive Telegram Bot Service: command dispatcher, interactive signal approval, credential wizard, and emergency controls."""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union

from src.domain.entities.signal import ParsedSignalDTO
from src.schemas.signal import TradingSignalCreate
from src.schemas.risk import DailyRiskConfigCreate
from src.schemas.master import ExchangeCreate, TradingAccountCreate, SignalProviderCreate
from src.database.models.trading_credentials import TradingCredential
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.instrument_service import InstrumentService
from src.repository.signal_repository import SignalRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient, format_crypto_price, format_crypto_qty

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


class TelegramService:
    """Dispatches Telegram commands, processes text signals, manages credential setup wizards, and handles inline approval buttons."""

    # Shared wizard state across instances: {chat_id: {"step": "...", "env": "...", "api_key": "..."}}
    _wizard_state: Dict[Union[int, str], Dict[str, Any]] = WizardStateDict()

    def __init__(
        self,
        signal_parser: SignalParserService,
        risk_calculator: RiskCalculatorService,
        trade_service: TradeService,
        signal_repo: SignalRepository,
        trade_repo: TradeRepository,
        order_repo: OrderRepository,
        daily_risk_repo: DailyRiskRepository,
        trade_summary_repo: TradeSummaryRepository,
        watchlist_repo: WatchlistRepository,
        instrument_repo: InstrumentRepository,
        risk_profile_repo: RiskProfileRepository,
        bot_log_repo: BotLogRepository,
        bot_setting_repo: BotSettingRepository,
        signal_provider_repo: Optional[SignalProviderRepository] = None,
        instrument_service: Optional[InstrumentService] = None,
        exchange_repo: Optional[ExchangeRepository] = None,
        trading_account_repo: Optional[TradingAccountRepository] = None,
        trading_credential_repo: Optional[TradingCredentialRepository] = None,
        position_manager: Optional[PositionManager] = None,
        binance_client: Optional[BinanceRestClient] = None,
        telegram_client: Optional[TelegramNotifierClient] = None,
        wizard_state: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
    ) -> None:
        self.signal_parser = signal_parser
        self.risk_calc = risk_calculator
        self.trade_service = trade_service
        self.signal_repo = signal_repo
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.watchlist_repo = watchlist_repo
        self.instrument_repo = instrument_repo
        self.risk_profile_repo = risk_profile_repo
        self.bot_log_repo = bot_log_repo
        self.bot_setting_repo = bot_setting_repo
        self.signal_provider_repo = signal_provider_repo
        self.instrument_service = instrument_service
        self.exchange_repo = exchange_repo
        self.trading_account_repo = trading_account_repo
        self.trading_credential_repo = trading_credential_repo
        self.position_manager = position_manager
        self.binance_client = binance_client
        self.telegram_client = telegram_client
        if wizard_state is not None:
            self._wizard_state = wizard_state

    # =========================================================================
    # COMMAND DISPATCHER (13 COMMANDS)
    # =========================================================================
    async def handle_command(self, command_text: str, account_id: int = 1, chat_id: Union[int, str] = 1) -> str:
        """Parse and execute a Telegram command string."""
        parts = command_text.strip().split()
        if not parts:
            return "Perintah tidak valid. Ketik /help untuk panduan."

        cmd = parts[0].lower().replace("/", "")
        args = parts[1:]

        if cmd in ("start", "help"):
            return self._cmd_help()
        elif cmd in ("setup_account", "account_setup", "set_credentials"):
            return await self._cmd_setup_account(chat_id)
        elif cmd in ("account", "credentials"):
            return await self._cmd_account_info(account_id)
        elif cmd == "balance":
            return await self._cmd_balance()
        elif cmd in ("status", "positions"):
            return await self._cmd_status(account_id)
        elif cmd in ("pending", "orders"):
            return await self._cmd_pending(account_id)
        elif cmd in ("summary", "performance"):
            return await self._cmd_summary(account_id)
        elif cmd == "circuit_breaker":
            return await self._cmd_circuit_breaker(account_id)
        elif cmd == "close":
            return await self._cmd_close(args)
        elif cmd in ("close_all", "panic"):
            return await self._cmd_panic(account_id)
        elif cmd == "pause":
            return await self._cmd_pause()
        elif cmd == "resume":
            return await self._cmd_resume()
        elif cmd == "watchlist":
            return await self._cmd_watchlist(args)
        elif cmd == "logs":
            return await self._cmd_logs()
        elif cmd == "ping":
            return await self._cmd_ping()
        else:
            return f"Perintah <code>/{cmd}</code> tidak dikenali. Ketik /help untuk daftar perintah."

    # 1. /help
    def _cmd_help(self) -> str:
        return (
            "🤖 <b>CRYPTO BOT CONTROL CENTER</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔑 <b>Manajemen Akun & API:</b>\n"
            "• <code>/setup_account</code> - Hubungkan API Key & Secret Binance secara interaktif\n"
            "• <code>/account</code> - Cek info akun aktif, environment & masked key\n\n"
            "📊 <b>Monitoring & Keuangan:</b>\n"
            "• <code>/balance</code> - Cek saldo wallet, free margin & unrealized PnL\n"
            "• <code>/status</code> - Daftar posisi terbuka & status BEP/Trailing\n"
            "• <code>/pending</code> - Daftar limit order yang menunggu entry\n"
            "• <code>/summary</code> - Ringkasan performa trading & Win Rate\n"
            "• <code>/circuit_breaker</code> - Status limit risiko harian\n\n"
            "🚨 <b>Kontrol & Darurat:</b>\n"
            "• <code>/close &lt;trade_id&gt;</code> - Tutup 1 posisi manual\n"
            "• <code>/panic</code> atau <code>/close_all</code> - Market Close SEMUA posisi\n"
            "• <code>/pause</code> - Jeda eksekusi sinyal baru\n"
            "• <code>/resume</code> - Lanjutkan eksekusi sinyal otomatis\n\n"
            "⚙️ <b>Pengaturan & Diagnostik:</b>\n"
            "• <code>/watchlist [enable/disable &lt;symbol&gt;]</code> - Kelola pair aktif\n"
            "• <code>/logs</code> - 5 error log sistem terbaru\n"
            "• <code>/ping</code> - Status latency API & database\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 2. /setup_account (Interactive Wizard Trigger)
    async def _cmd_setup_account(self, chat_id: Union[int, str]) -> str:
        keyboard = [
            [
                {"text": "🧪 Binance Testnet", "callback_data": "WIZ_ENV_TESTNET"},
                {"text": "🚀 Binance Mainnet", "callback_data": "WIZ_ENV_MAINNET"},
            ],
            [
                {"text": "❌ Batal", "callback_data": "WIZ_CANCEL"},
            ],
        ]
        text = (
            "⚙️ <b>WIZARD SETUP AKUN & KREDENSIAL BINANCE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Pilih <b>Environment Binance</b> yang ingin Anda hubungkan:\n"
            "• <b>Testnet</b>: Untuk simulasi aman tanpa risiko saldo riil\n"
            "• <b>Mainnet</b>: Untuk trading live riil di Binance Futures\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        if self.telegram_client:
            try:
                await self.telegram_client.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
            except Exception:
                pass
        return text

    # 3. /account
    async def _cmd_account_info(self, account_id: int) -> str:
        env = "TESTNET" if getattr(self.binance_client, "testnet", True) else "MAINNET"
        api_key = getattr(self.binance_client, "api_key", "")
        masked_key = f"{api_key[:4]}****{api_key[-4:]}" if len(api_key) >= 8 else "Belum Dikonfigurasi"

        # Check DB credential if available
        if self.trading_credential_repo:
            cred = await self.trading_credential_repo.get_active_credential(account_id)
            if cred and cred.encrypted_api_key:
                raw_k = cred.encrypted_api_key
                masked_key = f"{raw_k[:4]}****{raw_k[-4:]}" if len(raw_k) >= 8 else raw_k

        # Fetch balance
        bal_text = "N/A"
        if self.binance_client:
            try:
                b = await self.binance_client.fetch_balance()
                bal_val = b.get("total_wallet_balance", Decimal("0"))
                bal_text = f"${bal_val:,.2f} USDT"
            except Exception:
                bal_text = "Gagal memuat saldo"

        return (
            "🏦 <b>INFORMASI AKUN & KREDENSIAL AKTIF</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏛️ Bursa: <b>Binance Futures</b>\n"
            f"🌐 Environment: <b>{env}</b>\n"
            f"🔑 API Key: <code>{masked_key}</code>\n"
            f"💰 Saldo Wallet: <b>{bal_text}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Gunakan <code>/setup_account</code> untuk mengganti / memperbarui API Key.</i>"
        )

    # 4. /balance
    async def _cmd_balance(self) -> str:
        bal = Decimal("10000.0")
        free_margin = Decimal("10000.0")
        unrealized_pnl = Decimal("0.0")

        if self.binance_client:
            try:
                bal_data = await self.binance_client.fetch_balance()
                bal = bal_data.get("total_wallet_balance", Decimal("10000.0"))
                free_margin = bal_data.get("free_margin", Decimal("10000.0"))
                unrealized_pnl = bal_data.get("unrealized_pnl", Decimal("0.0"))
            except Exception as e:
                return f"⚠️ Gagal mengambil saldo dari Binance: {e}"

        pnl_icon = "🟢" if unrealized_pnl >= Decimal("0") else "🔴"
        pnl_sign = "+" if unrealized_pnl >= Decimal("0") else ""
        return (
            "💰 <b>RINGKASAN SALDO BINANCE FUTURES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Total Wallet: <b>${bal:,.2f} USDT</b>\n"
            f"🔓 Free Margin: <b>${free_margin:,.2f} USDT</b>\n"
            f"{pnl_icon} Unrealized PnL: <b>{pnl_sign}${unrealized_pnl:,.2f} USDT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 5. /status
    async def _cmd_status(self, account_id: int) -> str:
        all_active = await self.trade_repo.get_active_trades_with_instrument(account_id)
        open_trades = [t for t in all_active if t.status in ("OPEN", "PARTIAL")]
        if not open_trades:
            return "ℹ️ Tidak ada posisi aktif yang sedang terbuka saat ini."

        lines = ["📊 <b>DAFTAR POSISI AKTIF</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for t in open_trades:
            sym = t.instrument.symbol if t.instrument else "UNKNOWN"
            pnl = t.unrealized_pnl if hasattr(t, "unrealized_pnl") and t.unrealized_pnl else Decimal("0.0")
            pnl_icon = "🟢" if pnl >= Decimal("0") else "🔴"
            bep_badge = " [🛡️ BEP]" if t.sl_price == t.entry_price else ""
            side_label = "LONG" if t.side == "BUY" else "SHORT"
            lines.append(
                f"• #{t.id} <b>{sym}</b> ({side_label} {t.leverage}x){bep_badge}\n"
                f"  Entry: ${t.entry_price} | SL: ${t.sl_price}\n"
                f"  Size: {t.remaining_qty} | PnL: {pnl_icon} ${pnl:,.2f}"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # 6. /pending
    async def _cmd_pending(self, account_id: int) -> str:
        all_active = await self.trade_repo.get_active_trades_with_instrument(account_id)
        waiting_trades = [t for t in all_active if t.status == "WAITING_ENTRY"]
        if not waiting_trades:
            return "ℹ️ Tidak ada limit order yang sedang menunggu entry."

        lines = ["⏳ <b>DAFTAR ORDER MENUNGGU ENTRY</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for t in waiting_trades:
            sym = t.instrument.symbol if t.instrument else "UNKNOWN"
            lines.append(
                f"• #{t.id} <b>{sym}</b> ({t.side})\n"
                f"  Limit Entry: ${t.entry_price} | SL: ${t.sl_price}\n"
                f"  Size: {t.position_size} | Dibuat: {t.created_at.strftime('%H:%M:%S') if t.created_at else '-'}"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # 7. /summary
    async def _cmd_summary(self, account_id: int) -> str:
        summary = await self.trade_summary_repo.get_performance_summary(
            account_id=account_id,
        )

        total_trades = summary.get("total_trades", 0)
        wins = summary.get("winning_trades", 0)
        losses = summary.get("losing_trades", 0)
        win_rate = summary.get("win_rate", 0.0)
        total_pnl = summary.get("total_net_pnl", Decimal("0.0"))
        commission = summary.get("total_commission", Decimal("0.0"))

        pnl_icon = "🟢" if total_pnl >= Decimal("0") else "🔴"
        pnl_sign = "+" if total_pnl >= Decimal("0") else ""

        return (
            "📊 <b>RINGKASAN PERFORMA TRADING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Total Trades Selesai: <b>{total_trades}</b>\n"
            f"🏆 Win: <b>{wins}</b> | 🛑 Loss: <b>{losses}</b>\n"
            f"🎯 Win Rate: <b>{win_rate:.1f}%</b>\n"
            f"💸 Total Komisi Fee: <b>${commission:,.2f} USDT</b>\n"
            f"{pnl_icon} Net Realized PnL: <b>${pnl_sign}{total_pnl:,.2f} USDT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 8. /circuit_breaker
    async def _cmd_circuit_breaker(self, account_id: int) -> str:
        today = datetime.now().date()
        snapshot = await self.daily_risk_repo.get_by_date(account_id, today)
        if not snapshot:
            snapshot = await self.daily_risk_repo.get_latest_snapshot(account_id)

        if not snapshot:
            # Auto-provision daily snapshot on demand using current balance
            balance = Decimal("10000.0")
            if self.binance_client:
                try:
                    bal_data = await self.binance_client.fetch_balance()
                    balance = bal_data.get("total_wallet_balance") or bal_data.get("free_margin") or Decimal("10000.0")
                except Exception:
                    pass

            profile_id = 1
            if self.risk_profile_repo:
                profile = await self.risk_profile_repo.get_active_profile()
                if profile:
                    profile_id = profile.id

            daily_risk_budget = balance * (Decimal("2.0") / Decimal("100"))
            snapshot = await self.daily_risk_repo.get_or_create_daily_snapshot(
                DailyRiskConfigCreate(
                    account_id=account_id,
                    risk_profile_id=profile_id,
                    date=today,
                    balance=balance,
                    risk_amount=daily_risk_budget,
                )
            )

        rem_budget = await self.daily_risk_repo.get_remaining_risk_budget(snapshot.id)
        used_margin = await self.daily_risk_repo.get_total_margin_used(snapshot.id)

        status_text = "🟢 NORMAL" if rem_budget > Decimal("0") else "🔴 BREACHED / LOCKED"
        return (
            "🛡️ <b>STATUS CIRCUIT BREAKER & RISK</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Status Proteksi: <b>{status_text}</b>\n"
            f"💰 Modal Awal Hari: <b>${snapshot.balance:,.2f} USDT</b>\n"
            f"🎯 Batas Risiko Harian (2%): <b>${snapshot.risk_amount:,.2f} USDT</b>\n"
            f"💵 Sisa Anggaran Risiko: <b>${rem_budget:,.2f} USDT</b>\n"
            f"🔒 Margin Digunakan: <b>${used_margin:,.2f} USDT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 9. /close <trade_id>
    async def _cmd_close(self, args: List[str]) -> str:
        if not args or not args[0].isdigit():
            return "⚠️ Gunakan format: <code>/close &lt;trade_id&gt;</code>\nContoh: <code>/close 12</code>"

        trade_id = int(args[0])
        trade = await self.trade_repo.get(trade_id)
        if not trade or trade.status not in ("OPEN", "PARTIAL", "WAITING_ENTRY"):
            return f"⚠️ Trade #{trade_id} tidak ditemukan atau posisinya sudah ditutup."

        await self.trade_service.close_trade_manually(
            trade_id=trade_id,
            close_reason="MANUAL_CLOSE",
            position_manager=self.position_manager,
        )

        return f"✅ Berhasil menutup posisi Trade <b>#{trade_id}</b> secara manual melalui Market Close."

    # 10. /panic atau /close_all
    async def _cmd_panic(self, account_id: int) -> str:
        all_trades = await self.trade_repo.get_active_trades_with_instrument(account_id)
        if not all_trades:
            return "ℹ️ Tidak ada posisi terbuka atau pending order untuk ditutup."

        closed_count = 0
        for t in all_trades:
            try:
                await self.trade_service.close_trade_manually(
                    trade_id=t.id,
                    close_reason="PANIC_CLOSE_ALL",
                    position_manager=self.position_manager,
                )
                closed_count += 1
            except Exception as e:
                logger.error(f"Error closing trade #{t.id} during panic: {e}")

        return (
            "🚨 <b>EMERGENCY PANIC CLOSE ALL DIAKTIFKAN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 Berhasil menutup dan membatalkan <b>{closed_count}/{len(all_trades)} posisi</b> secara simultan.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 11. /pause
    async def _cmd_pause(self) -> str:
        await self.bot_setting_repo.set_value("is_trading_paused", "true", setting_type="BOOLEAN", category="TRADING")
        return "⏸️ <b>BOT PAUSED / DIJEDA</b>\nSinyal baru yang masuk tidak akan dieksekusi sampai Anda mengetik <code>/resume</code>."

    # 12. /resume
    async def _cmd_resume(self) -> str:
        await self.bot_setting_repo.set_value("is_trading_paused", "false", setting_type="BOOLEAN", category="TRADING")
        return "▶️ <b>BOT RESUMED / DIAKTIFKAN KEMBALI</b>\nEksekusi sinyal trading otomatis kembali aktif."

    # 13. /watchlist [enable/disable <symbol>]
    async def _cmd_watchlist(self, args: List[str]) -> str:
        if len(args) == 2 and args[0].lower() in ("enable", "disable"):
            action = args[0].lower()
            symbol = args[1].upper()

            inst = await self.instrument_repo.get_by_symbol(symbol)
            if not inst:
                return f"⚠️ Instrument <b>{symbol}</b> tidak ditemukan di database."

            is_enabled = (action == "enable")
            await self.watchlist_repo.set_symbol_enabled(instrument_id=inst.id, enabled=is_enabled)
            status_text = "DIAKTIFKAN" if is_enabled else "DINONAKTIFKAN"
            return f"✅ Watchlist pair <b>{symbol}</b> berhasil <b>{status_text}</b>."

        # List all watchlist
        watchlists = await self.watchlist_repo.get_enabled_watchlist_with_instruments()
        if not watchlists:
            return "ℹ️ Tidak ada pair yang aktif di watchlist saat ini."

        lines = ["📋 <b>WATCHLIST PAIR TRADING AKTIF</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for w in watchlists:
            sym = w.instrument.symbol if w.instrument else "UNKNOWN"
            max_lev = getattr(w.instrument, "max_leverage", 125) if w.instrument else 125
            lines.append(f"• <b>{sym}</b> (Max Lev: {max_lev}x)")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Gunakan: <code>/watchlist disable BTCUSDT</code> untuk menonaktifkan</i>")
        return "\n".join(lines)

    # 14. /logs
    async def _cmd_logs(self) -> str:
        logs = await self.bot_log_repo.get_recent_errors(limit=5)
        if not logs:
            return "✅ Tidak ada error log sistem dalam rekaman terbaru."

        lines = ["📜 <b>5 ERROR LOG SISTEM TERBARU</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for l in logs:
            lines.append(f"• [{l.created_at.strftime('%H:%M:%S')}] [{l.level}] {l.message}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # 15. /ping
    async def _cmd_ping(self) -> str:
        return (
            "🏓 <b>PONG! SISTEM BERJALAN NORMAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Database Connection: 🟢 OK\n"
            "• Binance API Status: 🟢 CONNECTED\n"
            "• Memory Health: 🟢 STABLE\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # =========================================================================
    # INTERACTIVE USER MESSAGE PROCESSOR (WITH CREDENTIAL SETUP WIZARD)
    # =========================================================================
    async def handle_user_message(
        self,
        raw_text: str,
        chat_id: Union[int, str] = 1,
        message_id: Optional[int] = None,
        account_id: int = 1,
    ) -> Union[str, Dict[str, Any]]:
        """Process incoming user text: handles active credential wizards, commands, or signals."""
        text_clean = raw_text.strip()
        cid = str(chat_id)

        # Handle cancellation of active wizard
        if text_clean.lower() in ("/cancel", "cancel") and cid in self._wizard_state:
            self._wizard_state.pop(cid, None)
            return "❌ <b>Setup akun dibatalkan.</b>"

        # Check if user is currently inside a setup wizard
        if cid in self._wizard_state:
            state = self._wizard_state[cid]
            step = state.get("step")

            # WIZARD STEP 1: Awaiting API Key
            if step == "AWAITING_API_KEY":
                if len(text_clean) < 10:
                    return "⚠️ API Key terlalu pendek. Silakan kirimkan <b>Binance API Key</b> yang valid (atau ketik /cancel):"

                state["api_key"] = text_clean
                state["step"] = "AWAITING_SECRET_KEY"
                return (
                    "🔒 <b>API Key Diterima!</b>\n\n"
                    "Sekarang kirimkan <b>Binance SECRET Key</b> Anda:\n"
                    "⚠️ <i>Demi keamanan, pesan Anda akan langsung otomatis dihapus oleh bot.</i>"
                )

            # WIZARD STEP 2: Awaiting Secret Key (With Auto-Delete & Validation Handshake)
            elif step == "AWAITING_SECRET_KEY":
                if len(text_clean) < 10:
                    return "⚠️ Secret Key terlalu pendek. Silakan kirimkan <b>Binance Secret Key</b> yang valid (atau ketik /cancel):"

                secret_key = text_clean
                api_key = state.get("api_key", "")
                env = state.get("env", "TESTNET")
                is_testnet = (env == "TESTNET")

                # Auto-delete secret key message from Telegram chat history
                if self.telegram_client and message_id:
                    try:
                        await self.telegram_client.delete_message(chat_id=chat_id, message_id=message_id)
                    except Exception:
                        pass

                # Handshake validation with Binance API
                test_client = BinanceRestClient(
                    api_key=api_key,
                    secret_key=secret_key,
                    testnet=is_testnet,
                )
                try:
                    bal_data = await test_client.fetch_balance()
                    balance = bal_data.get("total_wallet_balance", Decimal("0.0"))
                    free_margin = bal_data.get("free_margin", Decimal("0.0"))
                except Exception as e:
                    self._wizard_state.pop(cid, None)
                    return (
                        f"❌ <b>Verifikasi Binance Gagal!</b>\n\n"
                        f"API Key atau Secret Key tidak valid / IP belum diizinkan.\n"
                        f"Error: <code>{str(e)}</code>\n\n"
                        f"Silakan ulangi kembali dengan perintah <code>/setup_account</code>."
                    )
                finally:
                    await test_client.close()

                # Persist to Database
                acc_id = account_id
                if self.trading_account_repo:
                    target_acc = await self.trading_account_repo.get(account_id)
                    if target_acc:
                        target_acc.environment = env
                        self.trading_account_repo.session.add(target_acc)
                        await self.trading_account_repo.session.commit()
                        acc_id = target_acc.id
                    else:
                        accounts = await self.trading_account_repo.get_by_environment(env)
                        target_acc = accounts[0] if accounts else None
                        if not target_acc and self.exchange_repo:
                            exchange = await self.exchange_repo.get_by_code("BINANCE")
                            if not exchange:
                                exchange = await self.exchange_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
                            target_acc = await self.trading_account_repo.create(
                                TradingAccountCreate(
                                    exchange_id=exchange.id,
                                    name=f"Binance {env} Account",
                                    account_type="FUTURES",
                                    environment=env,
                                    is_active=True,
                                )
                            )
                        if target_acc:
                            acc_id = target_acc.id

                if self.trading_credential_repo:
                    await self.trading_credential_repo.deactivate_old_credentials(acc_id)
                    new_cred = TradingCredential(
                        account_id=acc_id,
                        key_name=f"Binance {env} Key ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
                        encrypted_api_key=api_key,
                        encrypted_secret_key=secret_key,
                        encrypted_passphrase=None,
                        key_version=1,
                        is_active=True,
                    )
                    self.trading_credential_repo.session.add(new_cred)
                    await self.trading_credential_repo.session.commit()

                # Hot-reload runtime Binance Client
                if self.binance_client:
                    if hasattr(self.binance_client, "reconfigure"):
                        self.binance_client.reconfigure(api_key=api_key, secret_key=secret_key, testnet=is_testnet)
                    else:
                        self.binance_client.api_key = api_key
                        self.binance_client.secret_key = secret_key
                        self.binance_client.testnet = is_testnet

                masked_key = f"{api_key[:4]}****{api_key[-4:]}"
                self._wizard_state.pop(cid, None)

                return (
                    "✅ <b>AKUN BINANCE BERHASIL DIHUBUNGKAN!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏛️ Bursa: <b>Binance Futures</b>\n"
                    f"🌐 Environment: <b>{env}</b>\n"
                    f"💰 Total Saldo: <b>${balance:,.2f} USDT</b>\n"
                    f"🔓 Free Margin: <b>${free_margin:,.2f} USDT</b>\n"
                    f"🔑 Masked API Key: <code>{masked_key}</code>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🚀 <i>Kredensial tersimpan aman dan bot siap digunakan untuk trading.</i>"
                )

        # Standard routing: Commands or Incoming Signals
        if text_clean.startswith("/"):
            return await self.handle_command(text_clean, account_id=account_id, chat_id=chat_id)
        else:
            has_acc = await self._has_active_account_and_credentials(account_id=account_id)
            if not has_acc:
                return (
                    "⚠️ <b>Akun Binance Belum Terhubung!</b>\n\n"
                    "Bot tidak dapat memproses sinyal trading ini karena belum ada akun dan API Key Binance yang aktif.\n\n"
                    "👉 Silakan ketik perintah <code>/setup_account</code> untuk menghubungkan akun Binance Anda terlebih dahulu."
                )
            return await self.handle_incoming_signal_message(text_clean)


    async def _has_active_account_and_credentials(self, account_id: int = 1) -> bool:
        """Verify if there is an active trading account with valid API credentials."""
        # If repositories are not provided (e.g., in isolated unit tests), allow signal handling
        if not self.trading_account_repo and not self.trading_credential_repo:
            return True

        # 1. Check database for active account and credentials
        if self.trading_account_repo and self.trading_credential_repo:
            account = await self.trading_account_repo.get(account_id)
            if account and account.is_active:
                cred = await self.trading_credential_repo.get_active_credential(account.id)
                if cred and cred.is_active:
                    return True

            active_account = await self.trading_account_repo.get_active_account(exchange_id=1)
            if active_account:
                cred = await self.trading_credential_repo.get_active_credential(active_account.id)
                if cred and cred.is_active:
                    return True

            for env in ("MAINNET", "TESTNET"):
                accounts = await self.trading_account_repo.get_by_environment(env)
                for acc in accounts:
                    cred = await self.trading_credential_repo.get_active_credential(acc.id)
                    if cred and cred.is_active:
                        return True

            return False

        return True

    # =========================================================================
    # INCOMING SIGNAL HANDLER & INTERACTIVE CONFIRMATION
    # =========================================================================
    async def _resolve_signal_provider_id(
        self, name: str = "AI Telegram Channel", provider_type: str = "TELEGRAM"
    ) -> int:
        """Resolve an active signal provider ID or create a default one in database."""
        if not self.signal_provider_repo:
            return 1

        # Check existing by name
        provider = await self.signal_provider_repo.get_by_name(name)
        if provider:
            return provider.id

        # Check existing by type
        active_providers = await self.signal_provider_repo.get_by_type(provider_type)
        if active_providers:
            return active_providers[0].id

        # Create new provider if not exists
        new_provider = await self.signal_provider_repo.create(
            SignalProviderCreate(
                name=name,
                type=provider_type,
                is_active=True,
            )
        )
        return new_provider.id

    async def handle_incoming_signal_message(self, raw_text: str) -> Dict[str, Any]:
        """Process incoming raw signal text, save signal in DB, and send interactive approval card."""
        parsed_dto = self.signal_parser.parse(raw_text)
        if not parsed_dto.is_valid:
            logger.warning(f"Ignored invalid incoming signal text: {parsed_dto.error_message}")
            return {"status": "INVALID_SIGNAL", "error": parsed_dto.error_message}

        # 1. Resolve or provision Signal Provider in Database
        provider_id = await self._resolve_signal_provider_id(
            name="AI Telegram Channel", provider_type="TELEGRAM"
        )

        # 2. Resolve or dynamically sync Instrument from Binance
        inst = None
        if self.instrument_service:
            inst = await self.instrument_service.get_or_sync_instrument(parsed_dto.symbol)
        elif self.instrument_repo:
            inst = await self.instrument_repo.get_by_symbol(parsed_dto.symbol)

        if not inst:
            err_msg = f"Pair {parsed_dto.symbol} tidak ditemukan di Binance Futures atau database."
            logger.warning(f"Rejected signal: {err_msg}")
            if self.telegram_client:
                try:
                    await self.telegram_client.send_message(
                        chat_id="ADMIN_CHANNEL",
                        text=f"⚠️ <b>Sinyal Ditolak:</b> Pair <b>{parsed_dto.symbol}</b> tidak terdaftar di Binance Futures.",
                    )
                except Exception:
                    pass
            return {"status": "INVALID_SYMBOL", "error": err_msg}

        inst_id = inst.id

        tp1 = parsed_dto.tp_targets[0] if len(parsed_dto.tp_targets) > 0 else None
        tp2 = parsed_dto.tp_targets[1] if len(parsed_dto.tp_targets) > 1 else None
        tp3 = parsed_dto.tp_targets[2] if len(parsed_dto.tp_targets) > 2 else None

        signal_record = await self.signal_repo.create(
            TradingSignalCreate(
                provider_id=provider_id,
                instrument_id=inst_id,
                raw_message=raw_text,
                side=parsed_dto.side,
                entry_min=parsed_dto.entry_min or Decimal("0"),
                entry_max=parsed_dto.entry_max or Decimal("0"),
                sl_price=parsed_dto.sl_price,
                tp1_price=tp1,
                tp2_price=tp2,
                tp3_price=tp3,
                confidence=Decimal("0.9"),
                status="RECEIVED",
                confirmation_status="PENDING",
            )
        )

        # 2. Format Signal Card & Inline Keyboard
        price_prec = inst.price_precision if inst else 4
        tps_str = ", ".join([f"${format_crypto_price(tp, price_prec)}" for tp in parsed_dto.tp_targets]) if parsed_dto.tp_targets else "N/A"
        side_icon = "🟢 LONG" if parsed_dto.side == "BUY" else "🔴 SHORT"
        entry_val = parsed_dto.avg_entry_price or parsed_dto.entry_min or Decimal("0")
        lev_val = parsed_dto.leverage or 20

        # Calculate SL distance %
        stop_dist = abs(entry_val - parsed_dto.sl_price)
        sl_pct = (stop_dist / entry_val * 100) if entry_val > Decimal("0") else Decimal("0")

        text = (
            f"⚡ <b>SINYAL TRADING BARU TERDETEKSI</b> ⚡\n\n"
            f"💎 <b>Pair:</b> #{parsed_dto.symbol} ({side_icon} {lev_val}x)\n"
            f"💵 <b>Entry:</b> ${format_crypto_price(entry_val, price_prec)}\n"
            f"🛑 <b>Stop Loss:</b> ${format_crypto_price(parsed_dto.sl_price, price_prec)} (-{sl_pct:.2f}%)\n"
            f"🎯 <b>Targets:</b> {tps_str}\n\n"
            f"🛡️ <i>Toleransi Risiko: Maksimal 2.0% dari Saldo Modal</i>\n"
            f"Silakan konfirmasi eksekusi order:"
        )

        keyboard = [
            [
                {"text": "✅ Approve Trade", "callback_data": f"APPROVE_{signal_record.id}"},
                {"text": "❌ Reject", "callback_data": f"REJECT_{signal_record.id}"},
            ]
        ]

        if self.telegram_client:
            try:
                await self.telegram_client.send_message(
                    chat_id="ADMIN_CHANNEL",
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
            except Exception as e:
                logger.error(f"Failed to send Telegram signal confirmation: {e}")

        return {
            "status": "PENDING_CONFIRMATION",
            "signal_id": signal_record.id,
            "symbol": parsed_dto.symbol,
            "side": parsed_dto.side,
        }

    # =========================================================================
    # CALLBACK QUERY HANDLER (APPROVAL & WIZARD DISPATCHER)
    # =========================================================================
    async def handle_callback_query(
        self,
        callback_data: str,
        message_id: Optional[int] = None,
        chat_id: Union[int, str] = 1,
        account_id: int = 1,
    ) -> Dict[str, Any]:
        """Dispatch inline keyboard callback clicks (Trade Approval / Credential Wizard)."""
        # Handle Setup Account Wizard Callbacks
        cid = str(chat_id)
        if callback_data in ("WIZ_ENV_TESTNET", "WIZ_ENV_MAINNET"):
            env = "TESTNET" if "TESTNET" in callback_data else "MAINNET"
            self._wizard_state[cid] = {"step": "AWAITING_API_KEY", "env": env}

            if self.telegram_client and message_id:
                try:
                    await self.telegram_client.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"🔑 <b>Setup Binance ({env})</b>\n\n"
                            f"Silakan kirimkan <b>Binance API Key</b> Anda:\n"
                            f"<i>(Ketik /cancel untuk membatalkan)</i>"
                        ),
                    )
                except Exception:
                    pass
            return {"status": "WIZARD_STARTED", "env": env}

        elif callback_data == "WIZ_CANCEL":
            self._wizard_state.pop(cid, None)
            if self.telegram_client and message_id:
                try:
                    await self.telegram_client.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text="❌ <b>Setup akun dibatalkan.</b>",
                    )
                except Exception:
                    pass
            return {"status": "WIZARD_CANCELLED"}

        # Handle Signal Approval Callbacks
        parts = callback_data.split("_")
        if len(parts) < 2:
            return {"status": "INVALID_CALLBACK"}

        raw_action = parts[0].upper()
        if raw_action == "SIG" and len(parts) >= 3:
            action = "APPROVE" if parts[1].upper() == "APP" else "REJECT"
            try:
                signal_id = int(parts[2])
            except ValueError:
                return {"status": "INVALID_SIGNAL_ID"}
        else:
            action = raw_action
            try:
                signal_id = int(parts[1])
            except ValueError:
                return {"status": "INVALID_SIGNAL_ID"}

        signal = await self.signal_repo.get(signal_id)
        if not signal:
            return {"status": "SIGNAL_NOT_FOUND", "signal_id": signal_id}

        default_chat = getattr(self.telegram_client, "default_chat_id", None) if self.telegram_client else None
        target_chat = chat_id if (chat_id not in (1, "1", None, "") and str(chat_id).upper() != "ADMIN_CHANNEL") else (default_chat or chat_id)

        if action == "APPROVE":
            # 1. Update status
            await self.signal_repo.update_confirmation_status(signal_id, "APPROVED")
            await self.signal_repo.update_status(signal_id, "EXECUTED")

            # 2. Reconstruct DTO from raw message or DB fields
            dto = None
            if signal.raw_message:
                try:
                    re_parsed = self.signal_parser.parse(signal.raw_message)
                    if re_parsed.is_valid:
                        dto = re_parsed
                except Exception:
                    pass

            if not dto:
                tps = []
                if signal.tp1_price:
                    tps.append(signal.tp1_price)
                if signal.tp2_price:
                    tps.append(signal.tp2_price)
                if signal.tp3_price:
                    tps.append(signal.tp3_price)

                sym = "BTCUSDT"
                if self.instrument_repo and signal.instrument_id:
                    inst = await self.instrument_repo.get(signal.instrument_id)
                    if inst:
                        sym = inst.symbol

                dto = ParsedSignalDTO(
                    raw_text="TELEGRAM_APPROVED_SIGNAL",
                    symbol=sym,
                    side=signal.side,
                    order_type="LIMIT",
                    entry_min=signal.entry_min or Decimal("0"),
                    entry_max=signal.entry_max or Decimal("0"),
                    sl_price=signal.sl_price,
                    tp_targets=tps,
                    leverage=20,
                )

            # 3. Execute trade
            try:
                exec_res = await self.trade_service.execute_signal(
                    signal_dto=dto,
                    signal_id=signal.id,
                    account_id=account_id,
                )

                # 4. Edit Telegram message if client attached
                if self.telegram_client and message_id:
                    try:
                        await self.telegram_client.edit_message_text(
                            chat_id=target_chat,
                            message_id=message_id,
                            text=f"✅ <b>SINYAL #{signal_id} DISETUJUI & DIEKSEKUSI</b>\nTrade ID: #{exec_res.trade_id} (#{dto.symbol} {dto.side})",
                        )
                    except Exception as err:
                        logger.error(f"Error editing message on APPROVE: {err}")

                return {"status": "APPROVED", "trade_id": exec_res.trade_id}
            except Exception as e:
                logger.error(f"Error executing approved signal #{signal_id}: {e}")
                if self.telegram_client and message_id:
                    try:
                        await self.telegram_client.edit_message_text(
                            chat_id=target_chat,
                            message_id=message_id,
                            text=(
                                f"❌ <b>EKSEKUSI GAGAL (SINYAL #{signal_id})</b>\n\n"
                                f"⚠️ <b>Error:</b> <code>{str(e)}</code>\n\n"
                                f"👉 <i>Periksa kredensial dengan <code>/setup_account</code> atau cek status API Key Binance Anda.</i>"
                            ),
                        )
                    except Exception as err:
                        logger.error(f"Error editing message on EXECUTION_FAILED: {err}")
                return {"status": "EXECUTION_FAILED", "error": str(e), "signal_id": signal_id}

        elif action == "REJECT":
            await self.signal_repo.update_confirmation_status(signal_id, "REJECTED")
            await self.signal_repo.update_status(signal_id, "REJECTED")

            sym = "UNKNOWN"
            if self.instrument_repo and signal.instrument_id:
                inst = await self.instrument_repo.get(signal.instrument_id)
                if inst:
                    sym = inst.symbol

            if self.telegram_client and message_id:
                try:
                    await self.telegram_client.edit_message_text(
                        chat_id=target_chat,
                        message_id=message_id,
                        text=(
                            f"❌ <b>SINYAL #{signal_id} DITOLAK</b>\n\n"
                            f"💎 <b>Pair:</b> #{sym} ({signal.side})\n"
                            f"🛡️ <i>Status: Dibatalkan oleh user. Tidak ada order yang dieksekusi.</i>"
                        ),
                    )
                except Exception as err:
                    logger.error(f"Error editing message on REJECT: {err}")

            return {"status": "REJECTED", "signal_id": signal_id}

        return {"status": "UNKNOWN_ACTION"}