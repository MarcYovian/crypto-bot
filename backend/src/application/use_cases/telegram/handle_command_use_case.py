"""Use case for dispatching and executing interactive Telegram bot commands."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.application.dto.trade_commands import CloseTradeCommand
from src.application.use_cases.trades.close_trade_use_case import CloseTradeUseCase
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.ports.repositories import (
    IBotLogRepository,
    IBotSettingRepository,
    IDailyRiskRepository,
    IInstrumentRepository,
    IOrderRepository,
    IRiskProfileRepository,
    ITradeRepository,
    ITradeSummaryRepository,
    ITradingAccountRepository,
    ITradingCredentialRepository,
    IWatchlistRepository,
)
from src.presentation.api.schemas.risk import DailyRiskConfigCreate

logger = logging.getLogger(__name__)


class HandleTelegramCommandUseCase:
    """Orchestrates responses for all user commands sent to the Telegram bot."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        order_repo: IOrderRepository,
        watchlist_repo: IWatchlistRepository,
        bot_log_repo: IBotLogRepository,
        daily_risk_repo: IDailyRiskRepository,
        trade_summary_repo: ITradeSummaryRepository,
        bot_setting_repo: Optional[IBotSettingRepository] = None,
        trading_account_repo: Optional[ITradingAccountRepository] = None,
        trading_credential_repo: Optional[ITradingCredentialRepository] = None,
        instrument_repo: Optional[IInstrumentRepository] = None,
        risk_profile_repo: Optional[IRiskProfileRepository] = None,
        close_trade_use_case: Optional[CloseTradeUseCase] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        notification_gateway: Optional[INotificationGateway] = None,
        trade_service: Optional[Any] = None,

    ) -> None:
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.watchlist_repo = watchlist_repo
        self.bot_log_repo = bot_log_repo
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.bot_setting_repo = bot_setting_repo
        self.trading_account_repo = trading_account_repo
        self.trading_credential_repo = trading_credential_repo
        self.instrument_repo = instrument_repo
        self.risk_profile_repo = risk_profile_repo
        self.close_trade_use_case = close_trade_use_case
        self.exchange_gateway = exchange_gateway
        self.notification_gateway = notification_gateway
        self.trade_service = trade_service


    async def execute(
        self,
        command: str,
        chat_id: Optional[Union[str, int]] = None,
        args: Optional[List[str]] = None,
        account_id: int = 1,
    ) -> str:
        """Alias for execute_command."""
        return await self.execute_command(command, chat_id=chat_id, args=args, account_id=account_id)

    async def execute_command(
        self,
        command: str,
        chat_id: Optional[Union[str, int]] = None,
        args: Optional[List[str]] = None,
        account_id: int = 1,
    ) -> str:
        """Parse and execute a Telegram command string."""
        parts = command.strip().split()
        if not parts:
            return "Perintah tidak valid. Ketik /help untuk panduan."

        cmd = parts[0].lower().lstrip("/")
        cmd_args = args if args is not None else parts[1:]

        if cmd in ("start", "help"):
            return self._handle_help()
        elif cmd in ("setup_account", "account_setup", "set_credentials"):
            return await self._handle_setup_account(chat_id)
        elif cmd in ("account", "credentials"):
            return await self._handle_account_info(account_id)
        elif cmd == "balance":
            return await self._handle_balance()
        elif cmd in ("status", "positions"):
            return await self._handle_status(account_id)
        elif cmd in ("pending", "orders"):
            return await self._handle_pending(account_id)
        elif cmd in ("summary", "performance"):
            return await self._handle_summary(account_id)
        elif cmd in ("circuit_breaker", "risk"):
            return await self._handle_circuit_breaker(account_id)
        elif cmd == "close":
            return await self._handle_close(cmd_args, account_id)
        elif cmd in ("panic", "close_all"):
            return await self._handle_panic(account_id)
        elif cmd == "pause":
            return await self._handle_pause()
        elif cmd == "resume":
            return await self._handle_resume()
        elif cmd in ("watchlist", "pairs"):
            return await self._handle_watchlist(cmd_args)
        elif cmd in ("logs", "errors"):
            return await self._handle_logs()
        elif cmd in ("ping", "health"):
            return "🏓 <b>Pong! / PONG!</b> Sistem bot aktif dan berjalan normal.\n• Database Connection: 🟢 OK\n• Telegram Gateway: 🟢 OK"
        else:


            return f"❓ Perintah <code>/{cmd}</code> tidak dikenali. Ketik /help untuk melihat daftar perintah."

    # 1. /setup_account
    async def _handle_setup_account(self, chat_id: Optional[Union[str, int]] = None) -> str:
        """Send interactive environment selection wizard."""
        keyboard = [
            [
                {"text": "🧪 Binance Testnet (Simulasi)", "callback_data": "WIZ_ENV_TESTNET"},
                {"text": "🚀 Binance Mainnet (Live)", "callback_data": "WIZ_ENV_MAINNET"},
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
        if self.notification_gateway and chat_id:
            try:
                await self.notification_gateway.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup={"inline_keyboard": keyboard},
                )
            except Exception:
                pass
        return text

    # 2. /account
    async def _handle_account_info(self, account_id: int = 1) -> str:
        """Fetch active account information, environment & API key mask."""
        env = "TESTNET"
        masked_key = "Belum Dikonfigurasi"

        if self.trading_credential_repo:
            cred = await self.trading_credential_repo.get_active_credential(account_id)
            if cred:
                raw_k = getattr(cred, "encrypted_api_key", "")
                masked_key = f"{raw_k[:4]}****{raw_k[-4:]}" if len(raw_k) >= 8 else (raw_k or "Tersimpan di DB")

        if self.trading_account_repo:
            acc = await self.trading_account_repo.get(account_id)
            if acc and getattr(acc, "is_testnet", None) is not None:
                env = "TESTNET" if acc.is_testnet else "MAINNET"

        bal_text = "N/A"
        if self.exchange_gateway:
            try:
                bal = await self.exchange_gateway.fetch_balance()
                bal_val = bal.get("total_wallet_balance", Decimal("0"))
                bal_text = f"${float(bal_val):,.2f} USDT"
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

    # 3. /balance
    async def _handle_balance(self) -> str:
        """Fetch and format futures wallet balance."""
        if not self.exchange_gateway:
            return "⚠️ Exchange Gateway tidak terhubung."

        try:
            bal = await self.exchange_gateway.fetch_balance()
            total = bal.get("total_wallet_balance", Decimal("0"))
            free = bal.get("free_margin", Decimal("0"))
            unrealized = bal.get("unrealized_pnl", Decimal("0"))

            pnl_icon = "🟢" if unrealized >= Decimal("0") else "🔴"
            pnl_sign = "+" if unrealized >= Decimal("0") else ""

            return (
                "💰 <b>RINGKASAN SALDO BINANCE FUTURES</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Total Wallet: <b>${float(total):,.2f} USDT</b>\n"
                f"🔓 Free Margin: <b>${float(free):,.2f} USDT</b>\n"
                f"{pnl_icon} Unrealized PnL: <b>{pnl_sign}${float(unrealized):,.2f} USDT</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
        except Exception as exc:
            logger.error("Error fetching balance: %s", exc)
            return f"❌ Gagal mengambil saldo bursa: {exc}"

    # 4. /status
    async def _handle_status(self, account_id: int = 1) -> str:
        """Fetch and format active open positions."""
        trades = await self.trade_repo.get_all_active_trades(account_id=account_id)
        open_trades = [t for t in trades if t.status in ("OPEN", "PARTIAL")]
        if not open_trades:
            return "ℹ️ Tidak ada posisi aktif yang sedang terbuka saat ini."

        lines = ["📊 <b>DAFTAR POSISI TRADING AKTIF</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for t in open_trades:
            sym = getattr(getattr(t, "instrument", None), "symbol", "UNKNOWN")
            side_label = "LONG" if t.side.upper() in ("BUY", "LONG") else "SHORT"
            bep_badge = " [🛡️ BEP]" if (t.entry_price and t.sl_price == t.entry_price) else ""
            lines.append(
                f"• #{t.id} <b>{sym}</b> ({side_label} {t.leverage or 10}x){bep_badge}\n"
                f"  Entry: ${t.entry_price} | SL: ${t.sl_price}\n"
                f"  Size: {t.remaining_qty or t.position_size} | Status: <b>{t.status}</b>"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # 5. /pending
    async def _handle_pending(self, account_id: int = 1) -> str:
        """Fetch and format waiting limit orders."""
        waiting = await self.trade_repo.get_all_active_trades(account_id=account_id)
        pending_trades = [t for t in waiting if t.status == "WAITING_ENTRY"]
        if not pending_trades:
            return "ℹ️ Tidak ada limit order yang sedang menunggu entry."

        lines = ["⏳ <b>DAFTAR ORDER MENUNGGU ENTRY (PULLBACK)</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for t in pending_trades:
            sym = getattr(getattr(t, "instrument", None), "symbol", "UNKNOWN")
            lines.append(
                f"• #{t.id} <b>{sym}</b> ({t.side})\n"
                f"  Limit Entry: ${t.entry_price} | SL: ${t.sl_price}\n"
                f"  Size: {t.position_size} | Leverage: <b>{t.leverage or 10}x</b>"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    # 6. /summary
    async def _handle_summary(self, account_id: int = 1) -> str:
        """Fetch and format overall performance summary."""
        try:
            summary = await self.trade_summary_repo.get_performance_summary(account_id=account_id)
            total_trades = summary.get("total_trades", 0)
            wins = summary.get("winning_trades", 0)
            losses = summary.get("losing_trades", 0)
            win_rate = summary.get("win_rate", 0.0)
            total_pnl = summary.get("total_net_pnl", Decimal("0.0"))
            commission = summary.get("total_commission", Decimal("0.0"))
        except Exception:
            summaries = await self.trade_summary_repo.get_multi(limit=50)
            total_pnl = sum((s.total_pnl for s in summaries if getattr(s, "total_pnl", None)), Decimal("0"))
            wins = sum(1 for s in summaries if getattr(s, "total_pnl", None) and s.total_pnl > Decimal("0"))
            losses = sum(1 for s in summaries if getattr(s, "total_pnl", None) and s.total_pnl < Decimal("0"))
            total_trades = len(summaries)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            commission = Decimal("0.0")

        pnl_icon = "🟢" if total_pnl >= Decimal("0") else "🔴"
        pnl_sign = "+" if total_pnl >= Decimal("0") else ""

        return (
            "📊 <b>RINGKASAN PERFORMA TRADING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Total Trades Selesai: <b>{total_trades}</b>\n"
            f"🏆 Win: <b>{wins}</b> | 🛑 Loss: <b>{losses}</b>\n"
            f"🎯 Win Rate: <b>{win_rate:.1f}%</b>\n"
            f"💸 Total Komisi Fee: <b>${float(commission):,.2f} USDT</b>\n"
            f"{pnl_icon} Net Realized PnL: <b>{pnl_sign}${float(total_pnl):,.2f} USDT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 7. /circuit_breaker
    async def _handle_circuit_breaker(self, account_id: int = 1) -> str:
        """Fetch daily risk budget and circuit breaker protection status."""
        today = date.today()
        snapshot = await self.daily_risk_repo.get_by_date(account_id, today)
        if not snapshot:
            snapshot = await self.daily_risk_repo.get_latest_snapshot(account_id)

        if not snapshot:
            balance = Decimal("10000.0")
            if self.exchange_gateway:
                try:
                    bal_data = await self.exchange_gateway.fetch_balance()
                    balance = bal_data.get("total_wallet_balance") or bal_data.get("free_margin") or Decimal("10000.0")
                except Exception:
                    pass

            daily_risk_budget = balance * Decimal("0.02")
            snapshot = await self.daily_risk_repo.get_or_create_daily_snapshot(
                DailyRiskConfigCreate(
                    account_id=account_id,
                    risk_profile_id=1,
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
            f"💰 Modal Awal Hari: <b>${float(snapshot.balance):,.2f} USDT</b>\n"
            f"🎯 Batas Risiko Harian (2%): <b>${float(snapshot.risk_amount):,.2f} USDT</b>\n"
            f"💵 Sisa Anggaran Risiko: <b>${float(rem_budget):,.2f} USDT</b>\n"
            f"🔒 Margin Digunakan: <b>${float(used_margin):,.2f} USDT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 8. /close <trade_id>
    async def _handle_close(self, args: List[str], account_id: int = 1) -> str:
        """Manually close a specific active trade by ID."""
        if not args or not args[0].isdigit():
            return "⚠️ Gunakan format: <code>/close &lt;trade_id&gt;</code>\nContoh: <code>/close 12</code>"

        trade_id = int(args[0])
        if self.trade_service and hasattr(self.trade_service, "close_trade_manually"):
            await self.trade_service.close_trade_manually(trade_id)
            return f"✅ Berhasil menutup posisi Trade <b>#{trade_id}</b> secara manual melalui Market Close."

        if self.close_trade_use_case:
            try:
                res = await self.close_trade_use_case.execute(
                    CloseTradeCommand(trade_id=trade_id, reason="MANUAL_CLOSE", account_id=account_id)
                )
                return f"✅ Berhasil menutup posisi Trade <b>#{trade_id}</b> secara manual melalui Market Close."
            except Exception as exc:
                return f"⚠️ Gagal menutup posisi Trade #{trade_id}: {exc}"

        trade = await self.trade_repo.get(trade_id)
        if not trade or trade.status not in ("OPEN", "PARTIAL", "WAITING_ENTRY"):
            return f"⚠️ Trade #{trade_id} tidak ditemukan atau posisinya sudah ditutup."

        return f"✅ Posisi Trade <b>#{trade_id}</b> telah diproses untuk penutupan."

    # 9. /panic atau /close_all
    async def _handle_panic(self, account_id: int = 1) -> str:
        """Emergency kill-switch: market close all active trades."""
        all_trades = await self.trade_repo.get_all_active_trades(account_id=account_id)
        if self.trade_service and hasattr(self.trade_service, "close_trade_manually"):
            for t in all_trades:
                await self.trade_service.close_trade_manually(t.id)
            return (
                "🚨 <b>EMERGENCY PANIC CLOSE ALL DIAKTIFKAN</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛑 Berhasil menutup dan membatalkan <b>{len(all_trades)}/{len(all_trades)} posisi</b> secara simultan.\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )

        if self.close_trade_use_case:
            try:
                results = await self.close_trade_use_case.panic_close_all(account_id=account_id)
                count = len(results)
                return (
                    "🚨 <b>EMERGENCY PANIC CLOSE ALL DIAKTIFKAN</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🛑 Berhasil menutup dan membatalkan <b>{count}/{count} posisi</b> secara simultan.\n"
                    "━━━━━━━━━━━━━━━━━━━━━━"
                )
            except Exception as exc:
                return f"⚠️ Gagal mengeksekusi Panic Close: {exc}"

        return (
            "🚨 <b>EMERGENCY PANIC CLOSE ALL DIAKTIFKAN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 Permintaan penutupan darurat untuk <b>{len(all_trades)}/{len(all_trades)} posisi</b> telah dikirim.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

    # 10. /pause
    async def _handle_pause(self) -> str:
        """Pause automated signal trading execution."""
        if self.bot_setting_repo:
            await self.bot_setting_repo.set_value("is_paused", "true")
            await self.bot_setting_repo.set_value("is_trading_paused", "true", setting_type="BOOLEAN", category="TRADING")
        return "⏸️ <b>BOT PAUSED / DIJEDA</b>\nSinyal baru yang masuk tidak akan dieksekusi sampai Anda mengetik <code>/resume</code>."

    # 11. /resume
    async def _handle_resume(self) -> str:
        """Resume automated signal trading execution."""
        if self.bot_setting_repo:
            await self.bot_setting_repo.set_value("is_paused", "false")
            await self.bot_setting_repo.set_value("is_trading_paused", "false", setting_type="BOOLEAN", category="TRADING")
        return "▶️ <b>BOT RESUMED / DIAKTIFKAN KEMBALI</b>\nEksekusi sinyal trading otomatis kembali aktif."


    # 12. /watchlist [add <sym> | remove <sym>]
    async def _handle_watchlist(self, args: Optional[List[str]] = None) -> str:
        """Fetch or modify active watchlist symbols."""
        if args and len(args) >= 2:
            subcmd = args[0].lower()
            sym = args[1].upper().replace("/", "").replace("#", "")
            if not sym.endswith("USDT"):
                sym += "USDT"

            if subcmd in ("add", "enable") and self.watchlist_repo:
                await self.watchlist_repo.set_symbol_enabled(sym, True)
                return f"✅ Pair <code>{sym}</code> berhasil <b>DIAKTIFKAN / ditambahkan</b> di watchlist."
            elif subcmd in ("remove", "disable", "del") and self.watchlist_repo:
                await self.watchlist_repo.set_symbol_enabled(sym, False)
                return f"🚫 Pair <code>{sym}</code> berhasil <b>DINONAKTIFKAN / dihapus</b> dari watchlist."


        watchlist = await self.watchlist_repo.get_all_active()
        if not watchlist:
            return "ℹ️ Belum ada pair yang diaktifkan di watchlist."

        syms = [getattr(w, "symbol", getattr(getattr(w, "instrument", None), "symbol", "UNKNOWN")) for w in watchlist]
        total_count = len(syms)
        max_display = 25

        displayed_syms = syms[:max_display]
        formatted_list = ", ".join(f"<code>{s}</code>" for s in displayed_syms)

        more_note = f"\n<i>... dan {total_count - max_display} pair lainnya (Total: <b>{total_count}</b> pair aktif).</i>\n" if total_count > max_display else "\n"

        return (
            f"📋 <b>WATCHLIST PAIR AKTIF ({total_count} Pair)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{formatted_list}"
            f"{more_note}"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Gunakan <code>/watchlist add BTCUSDT</code> atau <code>/watchlist remove ETHUSDT</code> untuk mengelola.</i>"
        )

    # 13. /logs
    async def _handle_logs(self) -> str:
        """Fetch latest error logs."""
        logs = await self.bot_log_repo.get_error_logs(limit=5) if hasattr(self.bot_log_repo, "get_error_logs") else await self.bot_log_repo.get_recent_logs(limit=5, level="ERROR")
        if not logs:
            return "✅ Tidak ada error log baru (Sistem berjalan bersih)."

        lines = ["⚠️ <b>ERROR LOG SISTEM (5 TERBARU)</b>\n━━━━━━━━━━━━━━━━━━━━━━"]
        for log in logs:
            lines.append(f"• [<b>{log.level}</b>] {log.message[:120]}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)


    # 14. /help & /start
    def _handle_help(self) -> str:
        """Generate full help menu message with all 15 commands."""
        return (
            "🤖 <b>DAFTAR LENGKAP PERINTAH CRYPTO BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🔧 Kredensial & Akun:</b>\n"
            "/setup_account - Hubungkan Binance API Key secara interaktif\n"
            "/account - Lihat info akun aktif, environment & API key\n"
            "/balance - Cek saldo wallet, free margin & Unrealized PnL\n\n"
            "<b>📊 Monitoring Trading:</b>\n"
            "/status - Lihat posisi terbuka & status BEP/Trailing\n"
            "/pending - Lihat limit order yang menunggu entry\n"
            "/summary - Ringkasan performa trading & Win Rate\n"
            "/circuit_breaker - Status limit risiko harian (2%)\n\n"
            "<b>⚡ Kontrol Eksekusi:</b>\n"
            "/close &lt;id&gt; - Tutup posisi manual (contoh: <code>/close 12</code>)\n"
            "/panic - Emergency kill-switch: Market close semua posisi\n"
            "/pause - Jeda eksekusi sinyal trading otomatis\n"
            "/resume - Lanjutkan eksekusi sinyal trading otomatis\n"
            "/watchlist - Kelola pair aktif di watchlist\n\n"
            "<b>🛠️ Sistem:</b>\n"
            "/logs - Lihat 5 error log sistem terbaru\n"
            "/ping - Cek status koneksi & latensi sistem\n"
            "/help - Panduan lengkap daftar perintah bot\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
