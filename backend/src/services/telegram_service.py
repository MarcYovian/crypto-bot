import logging
from datetime import datetime
from pytz import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config.settings import settings
from src.database.connection import AsyncSessionLocal
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.services.signal_parser import SignalParserService, ParsedSignal
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult
from src.services.execution_engine import BinanceExecutionEngine

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class TelegramService:
    """
    Service Interface Telegram Async Modern.
    Menerima sinyal, memicu konfirmasi interactive inline button,
    perintah interaktif (/status, /summary, /close),
    menyimpan data sinyal/trade ke DB, dan menghubungkan eksekusi ke Binance.
    """

    def __init__(self, execution_engine: BinanceExecutionEngine, token: str = None, allowed_chat_id: int = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.allowed_chat_id = allowed_chat_id or settings.TELEGRAM_CHAT_ID
        self.execution_engine = execution_engine
        self.app = Application.builder().token(self.token).post_init(self._setup_bot_commands).build()
        self._register_handlers()

    async def _setup_bot_commands(self, application: Application):
        """Mendaftarkan menu tombol auto-complete perintah ke Telegram."""
        from telegram import BotCommand
        commands = [
            BotCommand("account", "Cek saldo & info akun Binance"),
            BotCommand("status", "Cek posisi trading & order aktif"),
            BotCommand("summary", "Laporan ringkasan performa trading"),
            BotCommand("close", "Tutup posisi manual (cth: /close SOLUSDT)"),
        ]
        await application.bot.set_my_commands(commands)

    def _register_handlers(self):
        self.app.add_handler(CommandHandler(["account", "balance"], self._cmd_account))
        self.app.add_handler(CommandHandler(["status", "positions"], self._cmd_status))
        self.app.add_handler(CommandHandler(["summary", "performance"], self._cmd_summary))
        self.app.add_handler(CommandHandler("close", self._cmd_close))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message_received))
        self.app.add_handler(CallbackQueryHandler(self._on_confirmation_callback))

    async def _cmd_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler perintah /account atau /balance: Menampilkan saldo & informasi akun Binance."""
        if not update.effective_chat or update.effective_chat.id != self.allowed_chat_id:
            return

        try:
            status_msg = await update.message.reply_text("🔄 *Mengambil saldo akun dari Binance...*", parse_mode="Markdown")
            
            # Fetch balance via Hybrid Connector Engine
            balance_data = await self.execution_engine.fetch_balance()
            usdt_info = balance_data.get("USDT", {})
            
            total_equity = float(usdt_info.get("total") or 0.0)
            free_balance = float(usdt_info.get("free") or usdt_info.get("availableBalance") or 0.0)
            used_margin = float(usdt_info.get("used") or (total_equity - free_balance))

            env_mode = "Demo / Live Trading" if not settings.BINANCE_TESTNET else "Testnet"

            msg = (
                f"🏦 *INFORMASI AKUN BINANCE FUTURES*\n\n"
                f"• Mode Koneksi: `{env_mode}`\n"
                f"• Asset Utama: `USDT`\n\n"
                f"💰 *Detail Saldo (USDT):*\n"
                f"• Total Equity: `${total_equity:,.2f} USDT`\n"
                f"• Saldo Bebas (Available): `${free_balance:,.2f} USDT`\n"
                f"• Margin Terpakai (Used): `${used_margin:,.2f} USDT`\n\n"
                f"⚙️ *Konfigurasi Risk:*\n"
                f"• Default Leverage: `{settings.DEFAULT_LEVERAGE}x`\n"
                f"• Confidence Threshold: `{int(settings.CONFIDENCE_THRESHOLD * 100)}%`"
            )
            await status_msg.edit_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Gagal mengambil saldo Binance: {e}")
            await update.message.reply_text(f"❌ Gagal mengambil data saldo Binance: {str(e)}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler perintah /status atau /positions: Menampilkan posisi aktif."""
        if not update.effective_chat or update.effective_chat.id != self.allowed_chat_id:
            return

        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            active_trades = await trade_repo.get_active_trades()

        if not active_trades:
            await update.message.reply_text("ℹ️ Tidak ada posisi/trade aktif saat ini di database.", parse_mode="Markdown")
            return

        msg_lines = ["📊 *DAFTAR TRADING POSISI AKTIF:*"]
        for t in active_trades:
            side_emoji = "🟢 LONG" if t.side == "BUY" else "🔴 SHORT"
            msg_lines.append(
                f"\n🪙 *{t.symbol}* ({side_emoji})\n"
                f"• Status: `{t.status}` | Size: `{t.position_size}` (Leverage `{t.leverage}x`)\n"
                f"• Entry Target: `{t.entry_price}` | SL: `{t.sl_price}`\n"
                f"• TP1: `{t.tp1_price or '-'}` | TP2: `{t.tp2_price or '-'}` | TP3: `{t.tp3_price or '-'}`"
            )

        await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown")

    async def _cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler perintah /summary atau /performance: Rekapitulasi performa."""
        if not update.effective_chat or update.effective_chat.id != self.allowed_chat_id:
            return

        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            summary = await trade_repo.get_performance_summary()

        total = summary["total_trades"]
        if total == 0:
            await update.message.reply_text("ℹ️ Belum ada riwayat transaksi tertutup di statistik performa.", parse_mode="Markdown")
            return

        win_emoji = "🟢" if summary["total_net_pnl"] >= 0 else "🔴"
        msg = (
            f"📊 *REKAPITULASI PERFORMA TRADING (SYSTEM V2)*\n\n"
            f"• Total Sinyal Selesai: `{total}` Trade\n"
            f"• Win Rate: `{summary['winrate']:.1f}%` (`{summary['winning_trades']}` Win / `{summary['losing_trades']}` Loss)\n\n"
            f"💰 *Detail Keuangan (USDT):*\n"
            f"• Gross PnL: `${summary['total_gross_pnl']:+.2f}`\n"
            f"• Est. Komisi Binance: `-${summary['total_commission']:.2f}`\n\n"
            f"{win_emoji} *NET PnL BERSIH: `${summary['total_net_pnl']:+.2f} USDT`*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler perintah /close [SYMBOL]: Penutupan darurat / manual dari Telegram."""
        if not update.effective_chat or update.effective_chat.id != self.allowed_chat_id:
            return

        if not context.args:
            await update.message.reply_text("⚠️ Format salah. Gunakan: `/close [SYMBOL]` (Contoh: `/close BTCUSDT`)", parse_mode="Markdown")
            return

        symbol = context.args[0].upper()
        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            active_trades = await trade_repo.get_active_trades()
            target_trade = next((t for t in active_trades if t.symbol == symbol), None)

            if not target_trade:
                await update.message.reply_text(f"ℹ️ Tidak ditemukan posisi aktif untuk `{symbol}` di database.", parse_mode="Markdown")
                return

            # Tutup di Binance via CCXT
            try:
                exit_side = "sell" if target_trade.side == "BUY" else "buy"
                close_order = await self.execution_engine.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=exit_side,
                    amount=target_trade.remaining_qty,
                    params={"reduceOnly": True}
                )
                
                fill_price = float(close_order.get("price") or close_order.get("average") or target_trade.entry_price)
                await trade_repo.update_trade_status(target_trade.id, "CLOSED", closed_at=datetime.now())
                await trade_repo.log_event(target_trade.id, "MANUAL_CLOSE", f'{{"exit_price": {fill_price}}}')
                
                await update.message.reply_text(
                    f"✅ *Berhasil Menutup Posisi {symbol} (MANUAL_CLOSE)*\n\n"
                    f"• Close Price: `{fill_price}`\n"
                    f"• Size: `{target_trade.remaining_qty}`\n"
                    f"• Status: Posisi resmi ditutup.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Gagal close posisi manual {symbol}: {e}")
                await update.message.reply_text(f"❌ Gagal menutup posisi `{symbol}`: {e}", parse_mode="Markdown")

    async def _on_message_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_chat or update.effective_chat.id != self.allowed_chat_id:
            return

        raw_text = update.message.text or ""
        message_id = update.message.message_id

        # 1. Parse Sinyal
        parsed: ParsedSignal = SignalParserService.parse(raw_text)

        if not parsed.is_valid:
            logger.debug(f"Pesan diabaikan/gagal parse: {parsed.error_message}")
            return

        async with AsyncSessionLocal() as session:
            signal_repo = SignalRepository(session)

            # 2. Cek Duplicate Active Trade
            trade_repo = TradeRepository(session)
            if await trade_repo.has_active_trade_for_symbol(parsed.symbol, parsed.side):
                await update.message.reply_text(
                    f"⚠️ *Sinyal Diabaikan*: Masih ada posisi aktif untuk `{parsed.symbol}` ({parsed.side}).",
                    parse_mode="Markdown"
                )
                return

            # 3. Simpan Sinyal ke Database
            signal = await signal_repo.create_signal_from_parsed(parsed, telegram_message_id=message_id)

        # 4. Cek Confidence Threshold (UC-02 / FR-02)
        if parsed.confidence and parsed.confidence < settings.CONFIDENCE_THRESHOLD:
            await self._ask_user_confirmation(update, parsed, signal.id)
        else:
            # High Confidence -> Langsung Eksekusi Pipeline
            status_msg = await update.message.reply_text(
                f"✅ **Sinyal Valid Diterima!**\n\n"
                f"• Symbol: `{parsed.symbol}`\n"
                f"• Side: `{parsed.side}`\n"
                f"• Entry: `{parsed.entry_min} - {parsed.entry_max}`\n"
                f"• SL: `{parsed.sl_price}`\n"
                f"• Status: ⏳ Memproses Eksekusi ke Binance...",
                parse_mode="Markdown"
            )
            await self._process_trade_execution(signal.id, parsed, status_msg)

    async def _ask_user_confirmation(self, update: Update, parsed: ParsedSignal, signal_id: int):
        """Mengirim pesan konfirmasi interaktif dengan tombol Inline (Yes/No)."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Eksekusi (Yes)", callback_data=f"confirm_exec_{signal_id}"),
                InlineKeyboardButton("❌ Batalkan (No)", callback_data=f"confirm_cancel_{signal_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        conf_pct = int(parsed.confidence * 100) if parsed.confidence else 0
        await update.message.reply_text(
            f"⚠️ **Sinyal Confidence Rendah!** ({conf_pct}%)\n\n"
            f"• Symbol: `{parsed.symbol}`\n"
            f"• Side: `{parsed.side}`\n"
            f"• Entry: `{parsed.entry_min} - {parsed.entry_max}`\n"
            f"• SL: `{parsed.sl_price}`\n\n"
            f"Apakah Anda ingin melanjutkan eksekusi trade ini?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def _on_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("confirm_exec_"):
            signal_id = int(data.replace("confirm_exec_", ""))

            async with AsyncSessionLocal() as session:
                signal_repo = SignalRepository(session)
                await signal_repo.update_confirmation_status(signal_id, "APPROVED")
                signal = await signal_repo.get_by_id(signal_id)

            if not signal:
                await query.edit_message_text(text="❌ Data sinyal tidak ditemukan di database.")
                return

            await query.edit_message_text(text="🚀 **Sinyal Disetujui!** Memproses eksekusi order ke Binance...")

            # Re-construct ParsedSignal dari DB model
            parsed = ParsedSignal(
                symbol=signal.symbol,
                side=signal.side,
                entry_min=signal.entry_min,
                entry_max=signal.entry_max,
                sl_price=signal.sl_price,
                tp_prices=[p for p in [signal.tp1_price, signal.tp2_price, signal.tp3_price] if p],
                confidence=signal.confidence,
                is_valid=True
            )
            await self._process_trade_execution(signal_id, parsed, query.message)

        elif data.startswith("confirm_cancel_"):
            signal_id = int(data.replace("confirm_cancel_", ""))

            async with AsyncSessionLocal() as session:
                signal_repo = SignalRepository(session)
                await signal_repo.update_confirmation_status(signal_id, "APPROVED")
                await signal_repo.update_signal_status(signal_id, "REJECTED")

            await query.edit_message_text(text="🚫 **Sinyal Dibatalkan oleh Pengguna.**")

    async def _process_trade_execution(self, signal_id: int, parsed: ParsedSignal, status_msg):
        """Memproses alur kalkulasi risk management dan eksekusi order ke Binance."""
        today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")

        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            signal_repo = SignalRepository(session)

            # 1. Ambil Snapshot Risk Hari Ini
            daily_risk = await trade_repo.get_daily_risk(today_str)
            if not daily_risk:
                # Fallback jika belum ada snapshot: Buat snapshot darurat $1000 @ 2%
                daily_risk = await trade_repo.create_daily_risk_snapshot(today_str, balance=1000.0, risk_percent=2.0)

            # 2. Ambil Symbol Precision Info dari Exchange
            symbol_info = await self.execution_engine.fetch_symbol_info(parsed.symbol)

            # 3. Hitung Risk Management & Lot Size
            risk_res: RiskCalculationResult = RiskCalculatorService.calculate_position(
                daily_risk_amount=daily_risk.risk_amount,
                entry_price=parsed.entry_min,
                stop_loss_price=parsed.sl_price,
                side=parsed.side,
                max_leverage=settings.DEFAULT_LEVERAGE,
                symbol_info=symbol_info
            )

            if not risk_res.is_valid:
                await signal_repo.update_signal_status(signal_id, "REJECTED")
                await status_msg.reply_text(f"❌ *Eksekusi Gagal*: {risk_res.error_message}", parse_mode="Markdown")
                return

            # 4. Buat Record Trade & TradeRisk di DB
            trade = await trade_repo.create_trade_with_risk(
                signal_id=signal_id,
                symbol=parsed.symbol,
                side=parsed.side,
                leverage=settings.DEFAULT_LEVERAGE,
                risk_date=today_str,
                risk_res=risk_res,
                tp1_price=parsed.tp_prices[0] if len(parsed.tp_prices) > 0 else None,
                tp2_price=parsed.tp_prices[1] if len(parsed.tp_prices) > 1 else None,
                tp3_price=parsed.tp_prices[2] if len(parsed.tp_prices) > 2 else None,
            )

            # Set trade_repo ke execution engine
            self.execution_engine.trade_repo = trade_repo

            # 5. Eksekusi ke Binance Execution Engine
            exec_res = await self.execution_engine.execute_trade_pipeline(
                trade_id=trade.id,
                symbol=parsed.symbol,
                side=parsed.side,
                risk_res=risk_res,
                tp_prices=parsed.tp_prices,
                leverage=settings.DEFAULT_LEVERAGE,
                symbol_info=symbol_info
            )

            if exec_res.success:
                await signal_repo.update_signal_status(signal_id, "EXECUTED")
                await status_msg.reply_text(
                    f"🚀 *ORDER BERHASIL DIKIRIM KE BINANCE!*\n\n"
                    f"• Trade ID: `#{trade.id}`\n"
                    f"• Symbol: `{parsed.symbol}` ({parsed.side})\n"
                    f"• Type: `{exec_res.execution_type}`\n"
                    f"• Position Size: `{risk_res.position_size}`\n"
                    f"• Entry Price: `{risk_res.entry_price}`\n"
                    f"• Stop Loss: `{risk_res.stop_loss_price}`\n"
                    f"• Required Margin: `${risk_res.required_margin:.2f} USDT`",
                    parse_mode="Markdown"
                )
            else:
                await signal_repo.update_signal_status(signal_id, "REJECTED")
                await status_msg.reply_text(f"❌ *Eksekusi Binance Gagal*: {exec_res.error_message}", parse_mode="Markdown")

    def run(self):
        """Menjalankan bot dalam mode polling."""
        logger.info("Telegram Bot Listener berjalan...")
        self.app.run_polling()