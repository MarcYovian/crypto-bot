import asyncio
import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
import httpx
from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramNetworkError,
    TelegramSendError,
    TelegramMessageParseError,
)

logger = logging.getLogger(__name__)


def format_crypto_price(val: Any, precision: Optional[int] = None) -> str:
    """Format crypto price dynamically based on magnitude and precision without losing decimals."""
    if val is None:
        return "N/A"
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)
    if precision is not None and precision > 0:
        return f"{d:.{precision}f}"
    if abs(d) >= Decimal("1000"):
        return f"{d:,.2f}"
    elif abs(d) >= Decimal("1"):
        s = f"{d:.4f}".rstrip("0").rstrip(".")
        return s if "." in s else f"{d:.2f}"
    elif abs(d) > Decimal("0"):
        s = f"{d:.8f}".rstrip("0").rstrip(".")
        return s
    return "0.00"


def format_crypto_qty(val: Any, precision: Optional[int] = None) -> str:
    """Format crypto quantity cleanly without unnecessary trailing zeroes."""
    if val is None:
        return "0"
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)
    if precision is not None and precision > 0:
        s = f"{d:.{precision}f}".rstrip("0").rstrip(".") if "." in f"{d:.{precision}f}" else f"{d:.{precision}f}"
        return s if s else "0"
    s = f"{d:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


class TelegramNotifierClient:
    """Async client for Telegram Bot API notifications and interactive buttons."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        default_chat_id: Optional[Union[str, int]] = None,
        base_url: str = "https://api.telegram.org",
        timeout: float = 15.0,
    ) -> None:
        self.bot_token = bot_token or ""
        self.default_chat_id = default_chat_id
        self.base_url = f"{base_url.rstrip('/')}/bot{self.bot_token}"
        self.client = httpx.AsyncClient(timeout=timeout)

    def _handle_response_error(self, response: httpx.Response, operation: str) -> None:
        """Translate Telegram Bot API HTTP responses into Domain exceptions."""
        status_code = response.status_code
        try:
            body = response.json()
        except Exception:
            body = {"description": response.text}

        description = body.get("description", "Unknown Telegram error")
        details = {"operation": operation, "status_code": status_code, "body": body}

        if status_code == 401:
            raise TelegramAuthError(f"Unauthorized: {description}", details=details)
        elif status_code == 429:
            retry_after = body.get("parameters", {}).get("retry_after", 30)
            raise TelegramRateLimitError(
                f"Rate limit exceeded: {description}", retry_after=retry_after, details=details
            )
        elif status_code == 400:
            if "can't parse entities" in description.lower() or "entity" in description.lower():
                raise TelegramMessageParseError(f"Parse error: {description}", details=details)
            elif "chat not found" in description.lower() or "user is deactivated" in description.lower():
                raise TelegramSendError(f"Chat not found: {description}", details=details)
            else:
                raise TelegramSendError(f"Bad Request: {description}", details=details)
        elif status_code == 403:
            raise TelegramSendError(f"Forbidden (Bot blocked): {description}", details=details)
        else:
            raise TelegramError(f"Telegram API Error ({status_code}): {description}", details=details)

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Internal helper for executing POST requests to Telegram API."""
        if not self.bot_token:
            return {"ok": False, "description": "No bot token configured"}

        url = f"{self.base_url}/{endpoint}"
        try:
            response = await self.client.post(url, json=payload)
            if not response.is_success:
                self._handle_response_error(response, endpoint)
            data = response.json()
            return data.get("result", data)
        except httpx.TimeoutException as e:
            raise TelegramNetworkError(f"Timeout connecting to Telegram ({endpoint}): {e}") from e
        except httpx.NetworkError as e:
            raise TelegramNetworkError(f"Network error connecting to Telegram ({endpoint}): {e}") from e

    async def send_message(
        self,
        chat_id: Union[str, int],
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a formatted text message to a user or channel.
        
        Args:
            chat_id: Telegram target chat ID.
            text: Message text (supports HTML format).
            parse_mode: HTML or MarkdownV2.
            reply_markup: Optional InlineKeyboardMarkup dictionary.
            
        Returns:
            Sent Message object dict.
        """
        target_chat = self.default_chat_id if (chat_id in ("ADMIN_CHANNEL", None, "") and self.default_chat_id) else chat_id
        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await self._post("sendMessage", payload)

    async def set_my_commands(self, commands: Optional[List[Dict[str, str]]] = None) -> bool:
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
        try:
            res = await self._post("setMyCommands", {"commands": commands})
            return bool(res)
        except Exception:
            return False

    async def send_signal_confirmation(
        self,
        chat_id: Union[str, int],
        signal_id: Optional[int] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        entry_range: Optional[str] = None,
        sl: Optional[Decimal] = None,
        tp_targets: Optional[List[Decimal]] = None,
        confidence: Optional[Decimal] = None,
        text: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
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
        chat_id: Union[str, int],
        symbol: str,
        side: str,
        entry_price: Any,
        leverage: int,
        position_size: Any,
        margin: Any,
        sl_price: Any,
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
        """Send comprehensive trade open confirmation alert with exact price, size, and risk breakdown."""
        side_upper = side.upper()
        side_emoji = "🟢 BUY (LONG)" if side_upper == "BUY" else "🔴 SELL (SHORT)"
        base_asset = symbol.replace("USDT", "").replace("/", "")

        entry_dec = Decimal(str(entry_price)) if entry_price is not None else Decimal("0")
        sl_dec = Decimal(str(sl_price)) if sl_price is not None else Decimal("0")
        size_dec = Decimal(str(position_size)) if position_size is not None else Decimal("0")
        margin_dec = Decimal(str(margin)) if margin is not None else Decimal("0")

        # Calculate notional value if not provided
        notional_dec = Decimal(str(notional_value)) if notional_value is not None else (size_dec * entry_dec)

        # Calculate Stop Distance and SL percentage
        stop_dist = abs(entry_dec - sl_dec)
        sl_pct = (stop_dist / entry_dec * 100) if entry_dec > Decimal("0") else Decimal("0")
        sl_sign = "-" if side_upper == "BUY" else "+"

        # Format Risk Amount
        risk_amt_dec = Decimal(str(risk_amount)) if risk_amount is not None else (stop_dist * size_dec)
        risk_pct_str = f"{float(risk_percent):.1f}%" if risk_percent is not None else "2.0%"

        # Format Take Profits Breakdown
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
                    f"  • <b>TP{lvl} ({pct:.0f}% lot):</b> ${format_crypto_price(p, price_precision)} "
                    f"(+{profit_pct:.2f}%) ➔ <b>+${profit:,.2f} USDT</b>"
                )
        elif tp_targets:
            for i, tp in enumerate(tp_targets):
                tp_dec = Decimal(str(tp))
                tp_pct = (abs(tp_dec - entry_dec) / entry_dec * 100) if entry_dec > Decimal("0") else Decimal("0")
                tp_lines.append(f"  • <b>TP{i+1}:</b> ${format_crypto_price(tp_dec, price_precision)} (+{tp_pct:.2f}%)")

        tp_section = "\n".join(tp_lines) if tp_lines else "  <i>Tidak ada target Take Profit</i>"

        # Downscale note
        downscale_line = ""
        if is_leverage_downscaled and requested_leverage:
            downscale_line = f"\n⚠️ <i>Leverage di-downscale dari {requested_leverage}x ke {leverage}x (Batas Proteksi Likuidasi/Tier Bursa)</i>\n"

        text = (
            f"🚀 <b>ORDER EXECUTED — POSITION OPENED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol}\n"
            f"⚡ <b>Aksi:</b> {side_emoji} | <b>{leverage}x ISOLATED</b>\n"
            f"🛒 <b>Tipe Order:</b> {order_type} (Instant Fill)\n\n"
            f"📊 <b>RINCIAN POSISI & MARGIN:</b>\n"
            f"• <b>Entry Fill Price:</b> ${format_crypto_price(entry_dec, price_precision)}\n"
            f"• <b>Ukuran Posisi:</b> {format_crypto_qty(size_dec, qty_precision)} {base_asset}\n"
            f"• <b>Total Notional:</b> ${notional_dec:,.2f} USDT\n"
            f"• <b>Margin Digunakan:</b> ${margin_dec:,.2f} USDT\n\n"
            f"🛡️ <b>RISK MANAGEMENT (STRICT 2.0% GUARD):</b>\n"
            f"• <b>Stop Loss:</b> ${format_crypto_price(sl_dec, price_precision)} ({sl_sign}{sl_pct:.2f}%)\n"
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
        chat_id: Union[str, int],
        symbol: str,
        side: str,
        tp_level: int,
        exit_price: Any,
        closed_qty: Any,
        realized_pnl: Any,
        remaining_qty: Any,
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send partial take-profit fill alert."""
        pnl_dec = Decimal(str(realized_pnl)) if realized_pnl is not None else Decimal("0")
        pnl_emoji = "💰" if pnl_dec >= Decimal("0") else "⚠️"
        action_note = "🛡️ <i>SL otomatis digeser ke titik Break-Even (BEP)</i>" if tp_level == 1 else "📈 <i>Trailing SL aktif (SL di level TP1)</i>"
        base_asset = symbol.replace("USDT", "").replace("/", "")

        text = (
            f"🎯 <b>TAKE PROFIT {tp_level} HIT!</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Harga Exit TP{tp_level}:</b> ${format_crypto_price(exit_price, price_precision)}\n"
            f"{pnl_emoji} <b>Realized PnL:</b> +${pnl_dec:,.2f} USDT\n"
            f"📦 <b>Ukuran Ditutup:</b> {format_crypto_qty(closed_qty, qty_precision)} {base_asset}\n"
            f"📊 <b>Sisa Posisi:</b> {format_crypto_qty(remaining_qty, qty_precision)} {base_asset}\n\n"
            f"{action_note}"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_stop_loss_alert(
        self,
        chat_id: Union[str, int],
        symbol: str,
        side: str,
        exit_price: Any,
        closed_qty: Any,
        realized_pnl: Any,
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send Stop Loss hit alert."""
        pnl_dec = Decimal(str(realized_pnl)) if realized_pnl is not None else Decimal("0")
        base_asset = symbol.replace("USDT", "").replace("/", "")
        text = (
            f"🛑 <b>STOP LOSS TRIGGERED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Harga Exit SL:</b> ${format_crypto_price(exit_price, price_precision)}\n"
            f"📦 <b>Ukuran Ditutup:</b> {format_crypto_qty(closed_qty, qty_precision)} {base_asset}\n"
            f"📉 <b>Realized PnL:</b> -${abs(pnl_dec):,.2f} USDT\n\n"
            f"🛡️ <i>Posisi ditutup penuh untuk membatasi kerugian modal.</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_daily_summary_alert(
        self,
        chat_id: Union[str, int],
        date_str: str,
        starting_balance: Decimal,
        ending_balance: Decimal,
        net_pnl: Decimal,
        total_trades: int,
        win_rate: float,
    ) -> Dict[str, Any]:
        """Send Daily PnL and Performance summary report."""
        pnl_emoji = "🟢" if net_pnl >= Decimal("0") else "🔴"
        pnl_pct = ((ending_balance - starting_balance) / starting_balance * 100) if starting_balance > Decimal("0") else Decimal("0")

        text = (
            f"📊 <b>DAILY PERFORMANCE SUMMARY — {date_str}</b>\n\n"
            f"💰 <b>Initial Balance:</b> ${starting_balance:,.2f}\n"
            f"💵 <b>Closing Balance:</b> ${ending_balance:,.2f}\n"
            f"{pnl_emoji} <b>Net PnL:</b> ${net_pnl:+,.2f} ({pnl_pct:+.2f}%)\n"
            f"🔢 <b>Total Trades:</b> {total_trades}\n"
            f"🏆 <b>Win Rate:</b> {win_rate:.1f}%\n\n"
            f"🤖 <i>Automated Risk Snapshot locked at 00:00 WIB</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def edit_message_text(
        self,
        chat_id: Union[str, int],
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Edit an existing message text (e.g. after approval button is clicked)."""
        target_chat = self.default_chat_id if (str(chat_id).upper() in ("ADMIN_CHANNEL", "1", "NONE", "") and self.default_chat_id) else chat_id
        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        return await self._post("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Send toast notification acknowledgment for inline keyboard clicks."""
        payload: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text is not None:
            payload["text"] = text

        res = await self._post("answerCallbackQuery", payload)
        return bool(res)

    async def delete_message(
        self,
        chat_id: Union[str, int],
        message_id: int,
    ) -> bool:
        """Delete a message from chat history (useful for scrubbing sensitive secrets)."""
        target_chat = self.default_chat_id if (str(chat_id).upper() in ("ADMIN_CHANNEL", "1", "NONE", "") and self.default_chat_id) else chat_id
        payload = {
            "chat_id": target_chat,
            "message_id": message_id,
        }
        try:
            res = await self._post("deleteMessage", payload)
            return bool(res.get("result", False))
        except Exception:
            return False

    async def start_polling(
        self,
        on_message_coro,
        on_callback_query_coro=None,
    ) -> None:
        """Poll Telegram getUpdates and dispatch messages & inline button clicks."""
        self._is_polling = True
        offset = 0
        logger.info("Telegram Bot Long Polling loop active.")
        while getattr(self, "_is_polling", False):
            try:
                if not self.bot_token:
                    await asyncio.sleep(5)
                    continue
                url = f"{self.base_url}/getUpdates"
                payload = {"offset": offset, "timeout": 10, "allowed_updates": ["message", "channel_post", "callback_query"]}
                response = await self.client.post(url, json=payload, timeout=httpx.Timeout(25.0, connect=10.0))
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get("result", []):
                        offset = max(offset, update["update_id"] + 1)
                        msg = update.get("message") or update.get("channel_post")
                        if msg and on_message_coro:
                            txt = msg.get("text") or msg.get("caption") or ""
                            msg["text"] = txt
                            c_id = msg.get("chat", {}).get("id")
                            if txt:
                                logger.info(f"Received Telegram message: '{txt}' from chat_id={c_id}")
                                try:
                                    await on_message_coro(msg)
                                except Exception as err:
                                    logger.error(f"Error processing message: {err}")
                        elif "callback_query" in update and on_callback_query_coro:
                            cq = update["callback_query"]
                            c_data = cq.get("data", "")
                            c_id = cq.get("message", {}).get("chat", {}).get("id")
                            logger.info(f"Received Telegram callback: data='{c_data}' from chat_id={c_id}")
                            try:
                                await on_callback_query_coro(cq)
                            except Exception as err:
                                logger.error(f"Error processing callback: {err}")
                elif response.status_code == 409:
                    logger.warning("Telegram conflict (another instance polling). Retrying in 5s...")
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Telegram polling cycle notice: {e}")
                await asyncio.sleep(2)

    async def stop_polling(self) -> None:
        """Stop active Telegram long polling loop."""
        self._is_polling = False

    async def close(self) -> None:
        """Close the underlying HTTPX client session."""
        self._is_polling = False
        await self.client.aclose()


class TelegramChannelListener:
    """Async MTProto channel listener for Telegram VIP signals."""

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_name: str = "crypto_bot_session",
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.is_running = False

    async def start(
        self,
        channel_ids: List[Union[str, int]],
        on_message_coro,
    ) -> None:
        """Start listening for incoming messages on VIP channels."""
        self.is_running = True
        # Listening loop / telethon integration
        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop listening and disconnect session."""
        self.is_running = False

    async def disconnect(self) -> None:
        """Alias for stopping and disconnecting channel listener."""
        await self.stop()
