"""Domain event handlers for Trade events (Telegram notifications and WebSocket broadcasts)."""

import logging
from decimal import Decimal
from typing import Optional

from src.presentation.websocket.ws_manager import ws_manager
from src.domain.events.trade_events import (
    StopLossMovedEvent,
    TradeCancelledEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    TradePartiallyClosedEvent,
    TradeWaitingEntryEvent,
)
from src.domain.ports.gateways import INotificationGateway

logger = logging.getLogger(__name__)


class TradeNotificationEventHandler:
    """Listens to Trade Domain Events and triggers side-effects (Telegram alerts & WebSocket push)."""

    def __init__(self, notification_gateway: Optional[INotificationGateway] = None) -> None:
        self.notification_gateway = notification_gateway

    async def on_trade_opened(self, event: TradeOpenedEvent) -> None:
        """Handle TradeOpenedEvent: send rich Telegram card and push WebSocket."""
        logger.info("Handling TradeOpenedEvent for Trade #%s (%s)", event.trade_id, event.symbol)

        # 1. Send Rich Telegram Notification Card
        if self.notification_gateway:
            tp_targets = [tp for tp in (event.tp1_price, event.tp2_price, event.tp3_price) if tp is not None]
            notional = event.position_size * event.entry_price
            margin = notional / Decimal(str(event.leverage or 10))
            stop_dist = abs(event.entry_price - (event.sl_price or event.entry_price))
            risk_amt = stop_dist * event.position_size

            try:
                await self.notification_gateway.send_trade_opened_alert(
                    chat_id="ADMIN_CHANNEL",
                    symbol=event.symbol,
                    side=event.side.value if hasattr(event.side, "value") else str(event.side),
                    entry_price=event.entry_price,
                    leverage=event.leverage,
                    position_size=event.position_size,
                    margin=margin,
                    sl_price=event.sl_price,
                    tp_targets=tp_targets,
                    notional_value=notional,
                    risk_amount=risk_amt,
                    risk_percent=Decimal("2.0"),
                    order_type="MARKET",
                )
            except Exception as exc:
                logger.error("Failed sending trade opened telegram alert: %s", exc)

        # 2. Broadcast via WebSocket
        try:
            await ws_manager.broadcast(
                "TRADE_OPENED",
                {
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "side": event.side.value if hasattr(event.side, "value") else str(event.side),
                    "entry_price": float(event.entry_price),
                    "position_size": float(event.position_size),
                    "leverage": event.leverage,
                    "sl_price": float(event.sl_price) if event.sl_price else None,
                },
            )
        except Exception as exc:
            logger.warning("Failed broadcasting WebSocket TRADE_OPENED: %s", exc)

    async def on_trade_waiting_entry(self, event: TradeWaitingEntryEvent) -> None:
        """Handle TradeWaitingEntryEvent: send Limit order alert and push WebSocket."""
        logger.info("Handling TradeWaitingEntryEvent for Trade #%s (%s)", event.trade_id, event.symbol)

        if self.notification_gateway:
            side_badge = "🟢 BUY (LONG)" if (event.side.value if hasattr(event.side, "value") else str(event.side)).upper() in ("BUY", "LONG") else "🔴 SELL (SHORT)"
            notional = event.position_size * event.target_entry_price
            text = (
                f"⏳ <b>ORDER LIMIT TERPASANG (MENUNGGU PULLBACK)</b>\n\n"
                f"💎 <b>Pair:</b> #{event.symbol}\n"
                f"⚡ <b>Aksi:</b> {side_badge} | <b>{event.leverage}x ISOLATED</b>\n"
                f"📍 <b>Limit Entry Target:</b> ${event.target_entry_price}\n"
                f"📦 <b>Ukuran Posisi:</b> {event.position_size} ({float(notional):,.2f} USDT)\n"
                f"🛡️ <b>Stop Loss:</b> ${event.sl_price or 'N/A'}\n\n"
                f"⚙️ <i>Stop Loss dan Take Profit akan aktif otomatis di bursa ketika order Limit terisi.</i>"
            )
            try:
                await self.notification_gateway.send_message(text=text, chat_id="ADMIN_CHANNEL")
            except Exception as exc:
                logger.error("Failed sending limit order telegram alert: %s", exc)

        try:
            await ws_manager.broadcast(
                "LIMIT_ORDER_PLACED",
                {
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "side": event.side.value if hasattr(event.side, "value") else str(event.side),
                    "entry_price": float(event.target_entry_price),
                    "position_size": float(event.position_size),
                    "leverage": event.leverage,
                },
            )
        except Exception as exc:
            logger.warning("Failed broadcasting WebSocket LIMIT_ORDER_PLACED: %s", exc)

    async def on_trade_partially_closed(self, event: TradePartiallyClosedEvent) -> None:
        """Handle TradePartiallyClosedEvent: send TP hit alert and push WebSocket."""
        logger.info("Handling TradePartiallyClosedEvent for Trade #%s (%s)", event.trade_id, event.target_hit)

        if self.notification_gateway:
            try:
                tp_str = event.target_hit.value if hasattr(event.target_hit, "value") else str(event.target_hit)
                tier_num = 1 if "1" in tp_str else (2 if "2" in tp_str else 3)
                side_obj = getattr(event, "side", None)
                side_str = str(side_obj.value if hasattr(side_obj, "value") else side_obj) if side_obj is not None else "BUY"
                await self.notification_gateway.send_take_profit_alert(
                    chat_id="ADMIN_CHANNEL",
                    symbol=event.symbol,
                    side=side_str,
                    tp_level=tier_num,
                    exit_price=event.fill_price,
                    closed_qty=event.closed_qty,
                    realized_pnl=event.realized_pnl,
                    remaining_qty=event.remaining_qty,
                )
            except Exception as exc:
                logger.error("Failed sending partial close telegram alert: %s", exc)

        try:
            await ws_manager.broadcast(
                "POSITION_PARTIALLY_CLOSED",
                {
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "target_hit": event.target_hit.value if hasattr(event.target_hit, "value") else str(event.target_hit),
                    "exit_price": float(event.fill_price),
                    "closed_qty": float(event.closed_qty),
                    "remaining_qty": float(event.remaining_qty),
                    "realized_pnl": float(event.realized_pnl),
                },
            )
        except Exception as exc:
            logger.warning("Failed broadcasting WebSocket POSITION_PARTIALLY_CLOSED: %s", exc)

    async def on_stop_loss_moved(self, event: StopLossMovedEvent) -> None:
        """Handle StopLossMovedEvent: send alert and push WebSocket."""
        logger.info("Handling StopLossMovedEvent for Trade #%s (New SL: %s)", event.trade_id, event.new_sl_price)

        if self.notification_gateway:
            try:
                reason_text = "TP1 reached (Moved to Break-Even)" if "BEP" in event.reason.upper() else "Trailing Stop Adjusted"
                side_obj = getattr(event, "side", None)
                side_str = str(side_obj.value if hasattr(side_obj, "value") else side_obj) if side_obj is not None else "BUY"
                await self.notification_gateway.send_stop_loss_moved_alert(

                    chat_id="ADMIN_CHANNEL",
                    symbol=event.symbol,
                    side=side_str,
                    new_sl_price=event.new_sl_price,
                    old_sl_price=event.old_sl_price,
                    reason=reason_text,
                )
            except Exception as exc:
                logger.error("Failed sending SL moved telegram alert: %s", exc)

        try:
            await ws_manager.broadcast(
                "STOP_LOSS_UPDATED",
                {
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "new_sl_price": float(event.new_sl_price),
                    "reason": event.reason,
                },
            )
        except Exception as exc:
            logger.warning("Failed broadcasting WebSocket STOP_LOSS_UPDATED: %s", exc)

    async def on_trade_closed(self, event: TradeClosedEvent) -> None:
        """Handle TradeClosedEvent: send summary report and push WebSocket."""
        logger.info("Handling TradeClosedEvent for Trade #%s (PnL: %s)", event.trade_id, event.total_realized_pnl)

        if self.notification_gateway:
            try:
                side_str = (event.side.value if hasattr(event.side, "value") else str(event.side)) if event.side else "BUY"
                res_str = "WIN" if event.total_realized_pnl > 0 else ("LOSS" if event.total_realized_pnl < 0 else "BREAKEVEN")
                await self.notification_gateway.send_trade_closed_alert(
                    chat_id="ADMIN_CHANNEL",
                    symbol=event.symbol,
                    side=side_str,
                    exit_price=event.exit_price,
                    total_pnl=event.total_realized_pnl,
                    result=res_str,
                    close_reason=event.close_reason,
                )
            except Exception as exc:
                logger.error("Failed sending trade closed telegram alert: %s", exc)

        try:
            await ws_manager.broadcast(
                "TRADE_CLOSED",
                {
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "close_price": float(event.exit_price),
                    "pnl": float(event.total_realized_pnl),
                    "close_reason": event.close_reason,
                },
            )
        except Exception as exc:
            logger.warning("Failed broadcasting WebSocket TRADE_CLOSED: %s", exc)
