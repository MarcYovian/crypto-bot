"""Async Telegram bot that receives signals, handles confirmations, and triggers execution."""

import logging
from datetime import datetime
from pytz import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config.settings import settings
from src.database.connection import AsyncSessionLocal
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.services.signal_parser import SignalParserService, ParsedSignal
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult
from src.services.execution_engine import BinanceExecutionEngine
from src.services.trade_service import TradeService
from src.utils.error_parser import ErrorParser, FormattedError

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")


class TelegramService:
    """Async Telegram bot interface for receiving signals and controlling the bot.

    Handles:
    - Incoming messages → signal parsing → DB persistence → execution.
    - Low-confidence signals with interactive inline Yes/No confirmation.
    - Commands: ``/account``, ``/status``, ``/summary``, ``/close``.
    """

    def __init__(self, execution_engine: BinanceExecutionEngine, token: str = None, allowed_chat_id: int = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.allowed_chat_id = allowed_chat_id or settings.TELEGRAM_CHAT_ID
        self.execution_engine = execution_engine
        self.app = Application.builder().token(self.token).post_init(self._setup_bot_commands).build()
        self._register_handlers()

    async def _setup_bot_commands(self, application: Application):
        """Register the bot's command menu in Telegram (auto-complete hints)."""
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
        """Handle ``/account`` or ``/balance``: display Binance account info and USDT balance."""
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
            await update.message.reply_text(f"Failed to fetch Binance balance: {str(e)}")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ``/status`` or ``/positions``: show currently active trades."""
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
        """Handle ``/summary`` or ``/performance``: show aggregated trade performance."""
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
        funding_str = f"• Total Funding Fee: `-${summary['total_funding']:.2f}`\n" if summary.get('total_funding') else ""
        msg = (
            f"📊 *REKAPITULASI PERFORMA TRADING (SYSTEM V2)*\n\n"
            f"• Total Sinyal Selesai: `{total}` Trade\n"
            f"• Win Rate: `{summary['winrate']:.1f}%` (`{summary['winning_trades']}` Win / `{summary['losing_trades']}` Loss)\n\n"
            f"💰 *Detail Keuangan (USDT):*\n"
            f"• Gross PnL: `${summary['total_gross_pnl']:+.2f}`\n"
            f"• Est. Komisi Binance: `-${summary['total_commission']:.2f}`\n"
            f"{funding_str}\n"
            f"{win_emoji} *NET PnL BERSIH: `${summary['total_net_pnl']:+.2f} USDT`*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ``/close <SYMBOL>``: manually close a position from Telegram."""
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
        """Send an inline Yes/No keyboard asking the user to confirm a low-confidence signal."""
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
        """Execute the full risk-calculation → order-submission pipeline for a validated signal."""
        async with AsyncSessionLocal() as session:
            trade_repo = TradeRepository(session)
            signal_repo = SignalRepository(session)
            trade_service = TradeService(
                execution_engine=self.execution_engine, 
                trade_repo=trade_repo, 
                signal_repo=signal_repo
            )

            success_prep, msg_prep, prepared = await trade_service.prepare_trade(signal_id=signal_id, parsed=parsed)
            
            if not success_prep:
                formatted_err = ErrorParser.parse_error(msg_prep)
                err_text = formatted_err.to_telegram_markdown(symbol=parsed.symbol, side=parsed.side)
                await status_msg.reply_text(err_text, parse_mode="Markdown")
                return

            pre_info_msg = (
                f"📊 *PERSIAPAN EKSEKUSI TRADING*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 *Pair & Side*: `{parsed.symbol}` ({parsed.side})\n"
                f"🎯 *Entry Target*: `{prepared.risk_res.entry_price}`\n"
                f"🛡 *Stop Loss*: `{prepared.risk_res.stop_loss_price}`\n\n"
                f"⚙️ *Kalkulasi Risk & Margin:*\n"
                f"• Total Koin (Size): `{prepared.risk_res.position_size}` {parsed.symbol.replace('USDT', '')}\n"
                f"• Leverage Terpakai: `{settings.DEFAULT_LEVERAGE}x`\n"
                f"• Margin Diberdayakan: `${prepared.risk_res.required_margin:,.2f} USDT`\n"
                f"• Potensi Max Loss (Kerugian): `-${prepared.risk_res.risk_amount:,.2f} USDT` ({prepared.loss_pct:.1f}% Saldo)\n"
                f"• Sisa Saldo Tersedia: `${prepared.remaining_balance:,.2f} USDT`\n\n"
                f"⏳ *Mengirim order ke Binance Futures...*"
            )
            await status_msg.edit_text(pre_info_msg, parse_mode="Markdown")

            success_exec, msg_exec, exec_res = await trade_service.execute_trade(prepared=prepared)

            if success_exec:
                actual_entry = exec_res.actual_entry_price or prepared.risk_res.entry_price
                actual_margin = exec_res.actual_margin or prepared.risk_res.required_margin
                actual_sl_loss = exec_res.actual_sl_loss or prepared.risk_res.risk_amount

                post_info_msg = (
                    f"🚀 *ORDER BERHASIL DIEKSEKUSI DI BINANCE!*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• Trade ID: `#{prepared.trade_id}`\n"
                    f"• Symbol: `{parsed.symbol}` ({parsed.side})\n"
                    f"• Tipe Order: `{exec_res.execution_type}`\n\n"
                    f"💰 *Detail Posisi Realita Binance:*\n"
                    f"• Harga Beli Riil (Entry): `{actual_entry}` USDT\n"
                    f"• Total Koin (Qty): `{prepared.risk_res.position_size}` {parsed.symbol.replace('USDT', '')}\n"
                    f"• Total Margin Terpakai: `${actual_margin:,.2f} USDT`\n"
                    f"• Potensi Kerugian SL Riil: `-${actual_sl_loss:,.2f} USDT`\n"
                    f"• Entry Order ID: `{exec_res.entry_order_id}`\n"
                    f"• SL Order ID: `{exec_res.sl_order_id or 'Pending/Auto'}`\n\n"
                    f"✅ *Posisi aktif dan dipantau oleh sistem!*"
                )
                await status_msg.reply_text(post_info_msg, parse_mode="Markdown")
            else:
                formatted_err = ErrorParser.parse_error(msg_exec)
                err_text = formatted_err.to_telegram_markdown(symbol=parsed.symbol, side=parsed.side)
                await status_msg.reply_text(err_text, parse_mode="Markdown")

    def run(self):
        """Start the bot in polling mode (blocking)."""
        logger.info("Telegram Bot Listener started.")
        self.app.run_polling()