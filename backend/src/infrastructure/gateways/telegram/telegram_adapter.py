"""Telegram Notification Gateway Adapter implementing INotificationGateway."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.domain.ports.gateways import INotificationGateway
from src.infrastructure.gateways.telegram.telegram_connector import TelegramConnector
from src.infrastructure.gateways.telegram.telegram_formatter import TelegramFormatter

logger = logging.getLogger(__name__)


class TelegramNotificationAdapter(INotificationGateway):
    """Fulfills the INotificationGateway port via Telegram Bot API."""

    def __init__(
        self,
        connector: TelegramConnector,
        formatter: Optional[TelegramFormatter] = None,
        default_chat_id: Optional[Union[int, str]] = None,
    ) -> None:
        self.connector = connector
        self.formatter = formatter or TelegramFormatter()
        self.default_chat_id = str(default_chat_id) if default_chat_id else getattr(connector, "default_chat_id", None)

    async def send_message(
        self,
        text: str,
        chat_id: Optional[Union[int, str]] = None,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Send formatted text notification."""
        target_chat = (
            self.default_chat_id
            if (chat_id in ("ADMIN_CHANNEL", None, "") and self.default_chat_id)
            else (str(chat_id) if chat_id else self.default_chat_id)
        )

        if not target_chat:
            logger.debug("No chat_id specified and no default chat_id configured. Skipping send_message.")
            return {"ok": False, "error": "MISSING_CHAT_ID"}

        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self.connector.execute_api("sendMessage", payload)

    async def send_alert(
        self,
        title: str,
        message: str,
        level: str = "INFO",
        chat_id: Optional[Union[int, str]] = None,
    ) -> Dict[str, Any]:
        """Send formatted system or risk alert."""
        formatted_html = self.formatter.format_alert_html(title, message, level)
        return await self.send_message(text=formatted_html, chat_id=chat_id, parse_mode="HTML")

    async def send_signal_confirmation(
        self,
        chat_id: Optional[Union[str, int]] = None,
        signal_id: Optional[int] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        entry_range: Optional[str] = None,
        sl: Optional[Decimal] = None,
        tp_targets: Optional[List[Decimal]] = None,
        confidence: Optional[Decimal] = None,
        text: Optional[str] = None,
        reply_markup: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Send new trading signal alert with interactive Approve / Reject Inline buttons."""
        if text is not None:
            return await self.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        side_emoji = "🟢 BUY (LONG)" if side and side.upper() == "BUY" else "🔴 SELL (SHORT)"
        tp_lines = "\n".join([f"  🎯 <b>TP{i+1}:</b> {tp}" for i, tp in enumerate(tp_targets or [])])
        conf_str = f"\n📊 <b>Confidence:</b> {float(confidence)*100:.1f}%" if confidence else ""

        formatted_text = (
            f"⚡ <b>NEW SIGNAL RECEIVED — ACTION REQUIRED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol or 'UNKNOWN'}\n"
            f"📈 <b>Action:</b> {side_emoji}\n"
            f"🎯 <b>Entry Range:</b> {entry_range or 'N/A'}\n"
            f"🛡️ <b>Stop Loss:</b> {sl}\n"
            f"<b>Take Profit Targets:</b>\n{tp_lines}"
            f"{conf_str}\n\n"
            f"<i>Silakan setujui atau tolak sinyal ini:</i>"
        )

        inline_keyboard = reply_markup or {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve Trade", "callback_data": f"sig_app_{signal_id}"},
                    {"text": "❌ Reject", "callback_data": f"sig_rej_{signal_id}"},
                ]
            ]
        }

        return await self.send_message(
            chat_id=chat_id,
            text=formatted_text,
            parse_mode="HTML",
            reply_markup=inline_keyboard,
        )

    async def send_trade_opened_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        entry_price: Any = None,
        leverage: int = 1,
        position_size: Any = None,
        margin: Any = None,
        sl_price: Any = None,
        tp_targets: Optional[List[Any]] = None,
        notional_value: Optional[Any] = None,
        risk_amount: Optional[Any] = None,
        risk_percent: Optional[Any] = None,
        tp_allocations: Optional[List[Any]] = None,
        risk_reward_ratios: Optional[List[Any]] = None,
        requested_leverage: Optional[int] = None,
        is_leverage_downscaled: bool = False,
        leverage_reason: Optional[str] = None,
        order_type: str = "MARKET",
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send comprehensive trade open confirmation alert."""
        side_upper = side.upper()
        side_emoji = "🟢 BUY (LONG)" if side_upper == "BUY" else "🔴 SELL (SHORT)"
        base_asset = symbol.replace("USDT", "").replace("/", "")

        entry_dec = Decimal(str(entry_price)) if entry_price is not None else Decimal("0")
        sl_dec = Decimal(str(sl_price)) if sl_price is not None else Decimal("0")
        size_dec = Decimal(str(position_size)) if position_size is not None else Decimal("0")
        margin_dec = Decimal(str(margin)) if margin is not None else Decimal("0")

        notional_dec = Decimal(str(notional_value)) if notional_value is not None else (size_dec * entry_dec)
        stop_dist = abs(entry_dec - sl_dec)
        sl_pct = (stop_dist / entry_dec * 100) if entry_dec > Decimal("0") else Decimal("0")
        sl_sign = "-" if side_upper == "BUY" else "+"

        risk_amt_dec = Decimal(str(risk_amount)) if risk_amount is not None else (stop_dist * size_dec)
        risk_pct_str = f"{float(risk_percent):.1f}%" if risk_percent is not None else "2.0%"

        tp_lines = []
        if tp_allocations:
            for alloc in tp_allocations:
                lvl = getattr(alloc, "tp_level", 1)
                p = Decimal(str(getattr(alloc, "price", 0)))
                q = Decimal(str(getattr(alloc, "quantity", 0)))
                raw_pct = Decimal(str(getattr(alloc, "percentage", 0)))
                pct = raw_pct if raw_pct >= Decimal("1") else (raw_pct * Decimal("100"))
                profit = abs(p - entry_dec) * q
                profit_pct = (abs(p - entry_dec) / entry_dec * 100) if entry_dec > Decimal("0") else Decimal("0")
                tp_lines.append(
                    f"  • <b>TP{lvl} ({pct:.0f}% lot):</b> ${self.formatter.format_crypto_price(p, price_precision)} "
                    f"(+{profit_pct:.2f}%) ➔ <b>+${profit:,.2f} USDT</b>"
                )
        elif tp_targets:
            for i, tp in enumerate(tp_targets):
                tp_dec = Decimal(str(tp))
                tp_pct = (abs(tp_dec - entry_dec) / entry_dec * 100) if entry_dec > Decimal("0") else Decimal("0")
                tp_lines.append(f"  • <b>TP{i+1}:</b> ${self.formatter.format_crypto_price(tp_dec, price_precision)} (+{tp_pct:.2f}%)")

        tp_section = "\n".join(tp_lines) if tp_lines else "  <i>Tidak ada target Take Profit</i>"

        downscale_line = ""
        if is_leverage_downscaled and requested_leverage:
            downscale_line = f"\n⚠️ <i>Leverage di-downscale dari {requested_leverage}x ke {leverage}x (Batas Proteksi Likuidasi/Tier Bursa)</i>\n"

        text = (
            f"🚀 <b>ORDER EXECUTED — POSITION OPENED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol}\n"
            f"⚡ <b>Aksi:</b> {side_emoji} | <b>{leverage}x ISOLATED</b>\n"
            f"🛒 <b>Tipe Order:</b> {order_type} (Instant Fill)\n\n"
            f"📊 <b>RINCIAN POSISI & MARGIN:</b>\n"
            f"• <b>Entry Fill Price:</b> ${self.formatter.format_crypto_price(entry_dec, price_precision)}\n"
            f"• <b>Ukuran Posisi:</b> {self.formatter.format_crypto_qty(size_dec, qty_precision)} {base_asset}\n"
            f"• <b>Total Notional:</b> ${notional_dec:,.2f} USDT\n"
            f"• <b>Margin Digunakan:</b> ${margin_dec:,.2f} USDT\n\n"
            f"🛡️ <b>RISK MANAGEMENT (STRICT 2.0% GUARD):</b>\n"
            f"• <b>Stop Loss:</b> ${self.formatter.format_crypto_price(sl_dec, price_precision)} ({sl_sign}{sl_pct:.2f}%)\n"
            f"• <b>Maksimal Kerugian (SL):</b> -${risk_amt_dec:,.2f} USDT ({risk_pct_str} Modal)\n"
            f"{downscale_line}\n"
            f"🎯 <b>TARGET TAKE PROFIT:</b>\n"
            f"{tp_section}\n\n"
            f"⚙️ <b>AUTOMATION ACTIVE:</b>\n"
            f"• <i>TP1 Hit (50% lot): SL digeser otomatis ke Break-Even (BEP)</i>\n"
            f"• <i>TP2 Hit (30% lot): Trailing Stop otomatis ke harga TP1</i>\n"
            f"• <i>TP3/SL Hit: Seluruh sisa order exchange dibatalkan</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_take_profit_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        tp_level: int = 1,
        exit_price: Any = None,
        closed_qty: Any = None,
        realized_pnl: Any = None,
        remaining_qty: Any = None,
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send take profit fill notification."""
        pnl_dec = Decimal(str(realized_pnl or 0))
        pnl_sign = "+" if pnl_dec >= 0 else ""
        pnl_emoji = "💰" if pnl_dec >= 0 else "🔻"
        base_asset = symbol.replace("USDT", "").replace("/", "")

        sl_action = (
            "🛡️ <i>Stop Loss otomatis digeser ke Break-Even Point (BEP)</i>"
            if tp_level == 1
            else "📈 <i>Trailing Stop Loss aktif dan dikunci di profit target</i>"
        )

        text = (
            f"🎯 <b>TAKE PROFIT {tp_level} REACHED!</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Exit Price:</b> ${self.formatter.format_crypto_price(exit_price, price_precision)}\n"
            f"📦 <b>Lot Ditutup:</b> {self.formatter.format_crypto_qty(closed_qty, qty_precision)} {base_asset}\n"
            f"{pnl_emoji} <b>Realized PnL:</b> <b>{pnl_sign}${pnl_dec:,.2f} USDT</b>\n"
            f"⏳ <b>Sisa Posisi:</b> {self.formatter.format_crypto_qty(remaining_qty, qty_precision)} {base_asset}\n\n"
            f"{sl_action}"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_stop_loss_moved_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        new_sl_price: Any = None,
        reason: str = "TP1 reached (Moved to Break-Even)",
        old_sl_price: Optional[Any] = None,
        price_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send notification when SL is shifted to BEP or Trailing Stop."""
        old_str = f" (${self.formatter.format_crypto_price(old_sl_price, price_precision)})" if old_sl_price else ""
        text = (
            f"🛡️ <b>STOP LOSS ADJUSTED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"📍 <b>SL Baru:</b> <b>${self.formatter.format_crypto_price(new_sl_price, price_precision)}</b>{old_str}\n"
            f"ℹ️ <b>Alasan:</b> {reason}\n\n"
            f"<i>Posisi ini sekarang terlindungi dari risiko kerugian modal!</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_stop_loss_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        exit_price: Any = None,
        closed_qty: Any = None,
        realized_pnl: Any = None,
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send Stop Loss hit notification."""
        pnl_dec = Decimal(str(realized_pnl or 0))
        pnl_sign = "+" if pnl_dec >= 0 else ""
        base_asset = symbol.replace("USDT", "").replace("/", "")
        text = (
            f"🛑 <b>STOP LOSS TRIGGERED!</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Exit Price:</b> ${self.formatter.format_crypto_price(exit_price, price_precision)}\n"
            f"📦 <b>Lot Ditutup:</b> {self.formatter.format_crypto_qty(closed_qty, qty_precision)} {base_asset}\n"
            f"🔻 <b>Realized PnL:</b> <b>{pnl_sign}${pnl_dec:,.2f} USDT</b>\n\n"
            f"<i>Seluruh sisa pending orders pada exchange telah dibersihkan.</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


    async def send_trade_closed_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        exit_price: Any = None,
        total_pnl: Any = None,
        total_pnl_percent: Optional[Any] = None,
        result: str = "WIN",
        close_reason: str = "TP3 Hit",
        duration_minutes: Optional[int] = None,
        price_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send position close summary notification."""
        pnl_dec = Decimal(str(total_pnl or 0))
        pnl_sign = "+" if pnl_dec >= 0 else ""
        result_emoji = "🏆 WIN" if result.upper() == "WIN" else ("🛑 STOP LOSS" if "STOP" in close_reason.upper() else "ℹ️ CLOSED")
        dur_str = f"\n⏱️ <b>Durasi:</b> {duration_minutes} menit" if duration_minutes is not None else ""

        text = (
            f"🏁 <b>TRADE CLOSED — {result_emoji}</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Exit Price:</b> ${self.formatter.format_crypto_price(exit_price, price_precision)}\n"
            f"📊 <b>Total Realized PnL:</b> <b>{pnl_sign}${pnl_dec:,.2f} USDT</b>\n"
            f"ℹ️ <b>Alasan Penutupan:</b> {close_reason}{dur_str}\n\n"
            f"<i>Seluruh sisa pending orders pada exchange telah dibersihkan.</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_panic_close_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        closed_count: int = 0,
        total_realized_pnl: Optional[Decimal] = None,
        symbols_closed: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Send emergency panic close all broadcast alert."""
        symbols_str = ", ".join(symbols_closed) if symbols_closed else "All active pairs"
        pnl_str = f"\n💰 <b>Estimasi PnL:</b> ${total_realized_pnl:,.2f} USDT" if total_realized_pnl is not None else ""

        text = (
            f"🚨 <b>EMERGENCY PANIC CLOSE EXECUTED</b>\n\n"
            f"⚠️ <b>Kill-switch diaktifkan oleh Operator</b>\n"
            f"📦 <b>Posisi Ditutup:</b> {closed_count} posisi ({symbols_str})\n"
            f"🛑 <b>Semua open orders dibatalkan di bursa.</b>"
            f"{pnl_str}\n\n"
            f"<i>Bot dalam status siaga. Gunakan /resume untuk mengaktifkan kembali trading otomatis.</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_circuit_breaker_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        daily_loss_usdt: Any = None,
        daily_loss_percent: Any = None,
        max_daily_loss_percent: Any = None,
        total_balance: Any = None,
    ) -> Dict[str, Any]:
        """Send daily risk limit / circuit breaker trigger alert."""
        text = (
            f"🛑 <b>CIRCUIT BREAKER TRIGGERED — TRADING PAUSED</b>\n\n"
            f"⚠️ <i>Batas toleransi risiko harian telah tercapai!</i>\n\n"
            f"📉 <b>Kerugian Hari Ini:</b> -${float(daily_loss_usdt or 0):,.2f} USDT ({float(daily_loss_percent or 0):.2f}%)\n"
            f"🛡️ <b>Maksimal Loss Harian:</b> {float(max_daily_loss_percent or 5.0):.1f}%\n"
            f"💼 <b>Total Equity:</b> ${float(total_balance or 0):,.2f} USDT\n\n"
            f"🔒 <b>Tindakan Pengamanan:</b>\n"
            f"• Eksekusi sinyal otomatis dijeda hingga reset harian pukul 00:00 UTC\n"
            f"• Posisi terbuka yang ada tetap dikawal oleh SL & TP otomatis."
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_signal_rejected_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        reason: str = "",
        raw_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send notification when a signal is rejected."""
        text = (
            f"🚫 <b>SIGNAL REJECTED / DISCARDED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol or 'UNKNOWN'}\n"
            f"❌ <b>Alasan:</b> {reason}\n"
        )
        if raw_signal:
            snippet = raw_signal[:200] + ("..." if len(raw_signal) > 200 else "")
            text += f"\n📝 <b>Pesan Asli:</b>\n<code>{snippet}</code>"
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_price_runaway_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        signal_entry: Any = None,
        current_price: Any = None,
        deviation_percent: Any = None,
        reason: str = "Price moved > 2.0% away from entry",
    ) -> Dict[str, Any]:
        """Send alert when price deviates too far from signal entry."""
        text = (
            f"⚠️ <b>PRICE RUNAWAY — SIGNAL SKIPPED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol}\n"
            f"📍 <b>Target Sinyal:</b> ${signal_entry}\n"
            f"📊 <b>Harga Bursa Saat Ini:</b> ${current_price}\n"
            f"📈 <b>Deviasi:</b> {deviation_percent:.2f}% (Batas Aman: 2.0%)\n\n"
            f"🛡️ <i>Eksekusi dibatalkan untuk menghindari chasing market / bad entry risk.</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_daily_summary_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        date_str: str = "",
        total_trades: int = 0,
        win_count: int = 0,
        loss_count: int = 0,
        win_rate: float = 0.0,
        net_pnl_usdt: Decimal = Decimal("0"),
        profit_factor: float = 0.0,
    ) -> Dict[str, Any]:
        """Send end-of-day performance scorecard."""
        pnl_sign = "+" if net_pnl_usdt >= 0 else ""
        pnl_emoji = "🚀" if net_pnl_usdt >= 0 else "📉"
        text = (
            f"📊 <b>DAILY TRADING SCORECARD — {date_str}</b>\n\n"
            f"📦 <b>Total Posisi Selesai:</b> {total_trades}\n"
            f"✅ <b>Win:</b> {win_count} | ❌ <b>Loss:</b> {loss_count}\n"
            f"🎯 <b>Win Rate:</b> <b>{win_rate:.1f}%</b>\n"
            f"📈 <b>Profit Factor:</b> {profit_factor:.2f}\n\n"
            f"{pnl_emoji} <b>Net Realized PnL:</b> <b>{pnl_sign}${net_pnl_usdt:,.2f} USDT</b>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def edit_message_text(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Edit an existing sent message (for interactive wizards/cards)."""
        target_chat = (
            self.default_chat_id
            if (chat_id in ("ADMIN_CHANNEL", None, "") and self.default_chat_id)
            else str(chat_id)
        )

        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self.connector.execute_api("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        """Acknowledge an inline button click."""
        payload: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text

        return await self.connector.execute_api("answerCallbackQuery", payload)

    async def set_my_commands(
        self,
        commands: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Register bot commands to Telegram so they appear in the UI autocomplete menu."""
        if commands is None:
            commands = [
                {"command": "setup_account", "description": "Hubungkan Binance API Key secara interaktif"},
                {"command": "account", "description": "Lihat info akun aktif, environment & API key"},
                {"command": "balance", "description": "Cek saldo wallet & free margin"},
                {"command": "status", "description": "Lihat posisi terbuka & status BEP/Trailing"},
                {"command": "pending", "description": "Lihat limit order yang menunggu entry"},
                {"command": "summary", "description": "Ringkasan performa trading & Win Rate"},
                {"command": "circuit_breaker", "description": "Status limit risiko harian (2%)"},
                {"command": "close", "description": "Tutup posisi manual (/close <trade_id>)"},
                {"command": "panic", "description": "Emergency kill-switch: Market close semua posisi"},
                {"command": "pause", "description": "Jeda eksekusi sinyal trading otomatis"},
                {"command": "resume", "description": "Lanjutkan eksekusi sinyal trading otomatis"},
                {"command": "watchlist", "description": "Kelola pair aktif di watchlist"},
                {"command": "logs", "description": "Lihat 5 error log sistem terbaru"},
                {"command": "ping", "description": "Cek status & latensi sistem"},
                {"command": "help", "description": "Panduan lengkap daftar perintah bot"},
            ]
        payload = {"commands": commands}
        return await self.connector.execute_api("setMyCommands", payload)

    async def close(self) -> None:
        """Close the underlying Telegram HTTP session."""
        await self.connector.close()
