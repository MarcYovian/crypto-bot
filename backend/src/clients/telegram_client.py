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
        entry_price: Decimal,
        leverage: int,
        position_size: Decimal,
        margin: Decimal,
        sl_price: Decimal,
        tp_targets: List[Decimal],
    ) -> Dict[str, Any]:
        """Send trade open confirmation alert."""
        side_emoji = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        tp_lines = ", ".join([f"TP{i+1}: {tp}" for i, tp in enumerate(tp_targets)])

        text = (
            f"🚀 <b>POSITION OPENED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol}\n"
            f"⚡ <b>Side:</b> {side_emoji} ({leverage}x)\n"
            f"💵 <b>Entry Price:</b> ${entry_price:,.2f}\n"
            f"📦 <b>Size:</b> {position_size} (${margin:,.2f} Margin)\n"
            f"🛡️ <b>Stop Loss:</b> ${sl_price:,.2f}\n"
            f"🎯 <b>Targets:</b> {tp_lines}\n"
            f"⏰ <i>Order executed on Binance Futures</i>"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_take_profit_alert(
        self,
        chat_id: Union[str, int],
        symbol: str,
        side: str,
        tp_level: int,
        exit_price: Decimal,
        closed_qty: Decimal,
        realized_pnl: Decimal,
        remaining_qty: Decimal,
    ) -> Dict[str, Any]:
        """Send partial take-profit fill alert."""
        pnl_emoji = "💰" if realized_pnl >= Decimal("0") else "⚠️"
        action_note = "🛡️ <i>SL moved to Break-Even (BEP)</i>" if tp_level == 1 else "📈 <i>Trailing SL active</i>"

        text = (
            f"🎯 <b>TAKE PROFIT {tp_level} HIT!</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol}\n"
            f"💵 <b>Exit Price:</b> ${exit_price:,.2f}\n"
            f"{pnl_emoji} <b>Realized PnL:</b> +${realized_pnl:,.2f} USDT\n"
            f"📦 <b>Closed Size:</b> {closed_qty} (Remaining: {remaining_qty})\n\n"
            f"{action_note}"
        )
        return await self.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_stop_loss_alert(
        self,
        chat_id: Union[str, int],
        symbol: str,
        side: str,
        exit_price: Decimal,
        closed_qty: Decimal,
        realized_pnl: Decimal,
    ) -> Dict[str, Any]:
        """Send Stop Loss hit alert."""
        text = (
            f"🛑 <b>STOP LOSS TRIGGERED</b>\n\n"
            f"💎 <b>Pair:</b> #{symbol} ({side.upper()})\n"
            f"💵 <b>Exit Price:</b> ${exit_price:,.2f}\n"
            f"📦 <b>Closed Size:</b> {closed_qty}\n"
            f"📉 <b>Realized PnL:</b> ${realized_pnl:,.2f} USDT\n\n"
            f"🛡️ <i>Position closed to protect capital</i>"
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
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
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
        payload = {
            "chat_id": chat_id,
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
