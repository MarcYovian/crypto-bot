"""Position lifecycle and state machine management service."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict
from src.domain.entities.trade import OrderFillDTO
from src.domain.exceptions.trade import (
    TradeNotFoundError,
    InvalidTradeStateError,
    TradeExecutionError,
)
from src.schemas.order import ExecutionCreate, OrderCreate
from src.schemas.event_summary import TradeSummaryCreate
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient
from src.services.precision_filter import PrecisionFilterService
from src.api.websocket_manager import ws_manager


class PositionManager:
    """State machine handler for order fill events, dynamic BEP/Trailing adjustments, and trade closure."""

    def __init__(
        self,
        trade_repo: TradeRepository,
        order_repo: OrderRepository,
        execution_repo: ExecutionRepository,
        trade_event_repo: TradeEventRepository,
        trade_summary_repo: TradeSummaryRepository,
        daily_risk_repo: DailyRiskRepository,
        bot_setting_repo: Optional[BotSettingRepository] = None,
        risk_profile_repo: Optional[RiskProfileRepository] = None,
        binance_client: Optional[BinanceRestClient] = None,
        telegram_client: Optional[TelegramNotifierClient] = None,
    ) -> None:
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.bot_setting_repo = bot_setting_repo
        self.risk_profile_repo = risk_profile_repo
        self.binance_client = binance_client
        self.telegram_client = telegram_client

    async def handle_order_fill(self, fill: OrderFillDTO) -> None:
        """Process incoming order fill events from WebSocket stream or webhook.
        
        Args:
            fill: Standardized OrderFillDTO report.
        """
        trade = await self.trade_repo.get(fill.trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade {fill.trade_id} not found for fill event", trade_id=fill.trade_id)

        # 1. Record Execution
        realized_pnl = fill.realized_pnl
        if (realized_pnl is None or realized_pnl == Decimal("0")) and fill.purpose.upper() not in ("ENTRY", ""):
            if trade.entry_price:
                if trade.side.upper() == "BUY":
                    realized_pnl = (fill.fill_price - trade.entry_price) * fill.fill_qty
                else:
                    realized_pnl = (trade.entry_price - fill.fill_price) * fill.fill_qty

        await self.execution_repo.create(
            ExecutionCreate(
                order_id=fill.order_id,
                trade_id=fill.trade_id,
                price=fill.fill_price,
                qty=fill.fill_qty,
                commission=fill.fee,
                commission_asset=fill.fee_asset,
                realized_pnl=realized_pnl,
            )
        )

        purpose_upper = fill.purpose.upper()

        # CASE 1: ENTRY Fill
        if purpose_upper == "ENTRY":
            # Adjust planned position_size and remaining_qty if partial fill occurs
            if fill.fill_qty < trade.position_size:
                trade.position_size = fill.fill_qty
                trade.remaining_qty = fill.fill_qty

            await self.trade_repo.update_entry_fill(
                trade_id=trade.id,
                entry_price=fill.fill_price,
            )
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="ENTRY",
                payload={"fill_price": float(fill.fill_price), "fill_qty": float(fill.fill_qty)},
            )
            await ws_manager.broadcast(
                "ORDER_FILLED",
                {
                    "trade_id": trade.id,
                    "symbol": fill.symbol,
                    "purpose": "ENTRY",
                    "fill_price": float(fill.fill_price),
                    "fill_qty": float(fill.fill_qty),
                },
            )

        # CASE 2: TAKE PROFIT 1 Fill (Break-Even Protection Move)
        elif purpose_upper in ("TP1", "TAKE_PROFIT_1"):
            updated_trade = await self.trade_repo.reduce_position_qty(trade.id, closed_qty=fill.fill_qty)
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="TP1_HIT",
                payload={"fill_price": float(fill.fill_price), "realized_pnl": float(realized_pnl or 0)},
            )
            await ws_manager.broadcast(
                "TP_HIT",
                {
                    "trade_id": trade.id,
                    "symbol": fill.symbol,
                    "tp_level": 1,
                    "fill_price": float(fill.fill_price),
                    "realized_pnl": float(realized_pnl or 0),
                },
            )

            # Move SL to Break-Even (Entry price)
            await self._move_stop_loss(
                trade=trade,
                new_sl_price=trade.entry_price or Decimal("0"),
                is_bep=True,
                is_trailing=False,
                event_type="SL_MOVED_TO_BEP",
                sl_purpose="BEP_SL",
            )

            if self.telegram_client:
                try:
                    price_prec = trade.instrument.price_precision if getattr(trade, "instrument", None) else 4
                    qty_prec = trade.instrument.qty_precision if getattr(trade, "instrument", None) else 2
                    await self.telegram_client.send_take_profit_alert(
                        chat_id="ADMIN_CHANNEL",
                        symbol=fill.symbol,
                        side=trade.side,
                        tp_level=1,
                        exit_price=fill.fill_price,
                        closed_qty=fill.fill_qty,
                        realized_pnl=realized_pnl,
                        remaining_qty=updated_trade.remaining_qty if updated_trade else Decimal("0"),
                        price_precision=price_prec,
                        qty_precision=qty_prec,
                    )
                except Exception:
                    pass

        # CASE 3: TAKE PROFIT 2 Fill (Trailing SL Move)
        elif purpose_upper in ("TP2", "TAKE_PROFIT_2"):
            updated_trade = await self.trade_repo.reduce_position_qty(trade.id, closed_qty=fill.fill_qty)
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="TP2_HIT",
                payload={"fill_price": float(fill.fill_price), "realized_pnl": float(realized_pnl or 0)},
            )
            await ws_manager.broadcast(
                "TP_HIT",
                {
                    "trade_id": trade.id,
                    "symbol": fill.symbol,
                    "tp_level": 2,
                    "fill_price": float(fill.fill_price),
                    "realized_pnl": float(realized_pnl or 0),
                },
            )

            # Move SL to TP1 level
            tp1_orders = await self.order_repo.get_orders_by_purpose(trade.id, "TP1") or await self.order_repo.get_orders_by_purpose(trade.id, "TAKE_PROFIT_1")
            tp1_order = tp1_orders[0] if tp1_orders else None
            trailing_price = tp1_order.price if tp1_order else trade.entry_price

            await self._move_stop_loss(
                trade=trade,
                new_sl_price=trailing_price or Decimal("0"),
                is_bep=False,
                is_trailing=True,
                event_type="TRAILING_SL_UPDATED",
                sl_purpose="TRAILING_SL",
            )

            if self.telegram_client:
                try:
                    price_prec = trade.instrument.price_precision if getattr(trade, "instrument", None) else 4
                    qty_prec = trade.instrument.qty_precision if getattr(trade, "instrument", None) else 2
                    await self.telegram_client.send_take_profit_alert(
                        chat_id="ADMIN_CHANNEL",
                        symbol=fill.symbol,
                        side=trade.side,
                        tp_level=2,
                        exit_price=fill.fill_price,
                        closed_qty=fill.fill_qty,
                        realized_pnl=realized_pnl,
                        remaining_qty=updated_trade.remaining_qty if updated_trade else Decimal("0"),
                        price_precision=price_prec,
                        qty_precision=qty_prec,
                    )
                except Exception:
                    pass

        # CASE 4: TAKE PROFIT 3 / Final TP Fill (Full Take Profit Closure)
        elif purpose_upper in ("TP3", "TAKE_PROFIT_3"):
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="TP3",
                payload={"fill_price": float(fill.fill_price), "realized_pnl": float(realized_pnl or 0)},
            )
            await ws_manager.broadcast(
                "TP_HIT",
                {
                    "trade_id": trade.id,
                    "symbol": fill.symbol,
                    "tp_level": 3,
                    "fill_price": float(fill.fill_price),
                    "realized_pnl": float(realized_pnl or 0),
                },
            )
            await self.trade_repo.reduce_position_qty(trade_id=trade.id, closed_qty=fill.fill_qty)
            await self.finalize_trade_closure(
                trade_id=trade.id,
                close_reason="TP3_HIT",
                result_type="WIN",
                exit_price=fill.fill_price,
                closed_qty=fill.fill_qty,
            )

        # CASE 5: STOP LOSS Fill (SL Closure)
        elif purpose_upper in ("SL", "STOP_LOSS", "BEP_SL", "TRAILING_SL"):
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="SL",
                payload={"fill_price": float(fill.fill_price), "realized_pnl": float(realized_pnl or 0)},
            )
            await ws_manager.broadcast(
                "SL_HIT",
                {
                    "trade_id": trade.id,
                    "symbol": fill.symbol,
                    "fill_price": float(fill.fill_price),
                    "realized_pnl": float(realized_pnl or 0),
                },
            )
            await self.trade_repo.reduce_position_qty(trade_id=trade.id, closed_qty=fill.fill_qty)
            await self.finalize_trade_closure(
                trade_id=trade.id,
                close_reason="SL_HIT",
                exit_price=fill.fill_price,
                closed_qty=fill.fill_qty,
            )

    async def _move_stop_loss(
        self,
        trade: Any,
        new_sl_price: Decimal,
        is_bep: bool,
        is_trailing: bool,
        event_type: str,
        sl_purpose: str = "SL",
    ) -> None:
        """Helper to cancel existing exchange SL order and replace it with new defensive SL."""
        sym = trade.instrument.symbol if getattr(trade, "instrument", None) else "BTCUSDT"
        
        # Round new SL price according to instrument tick size & precision
        if getattr(trade, "instrument", None):
            inst = trade.instrument
            new_sl_price = PrecisionFilterService.round_price(
                new_sl_price,
                tick_size=inst.tick_size,
                price_precision=inst.price_precision,
            )

        # 1. Find existing SL order in DB
        sl_orders = (
            await self.order_repo.get_orders_by_purpose(trade.id, "SL")
            or await self.order_repo.get_orders_by_purpose(trade.id, "STOP_LOSS")
            or await self.order_repo.get_orders_by_purpose(trade.id, "BEP_SL")
            or await self.order_repo.get_orders_by_purpose(trade.id, "TRAILING_SL")
        )
        old_sl_order = sl_orders[0] if sl_orders else None

        # 2. Cancel old SL on Binance
        if old_sl_order and self.binance_client and old_sl_order.exchange_order_id:
            try:
                await self.binance_client.cancel_order(
                    symbol=sym,
                    order_id=old_sl_order.exchange_order_id,
                )
            except Exception:
                pass

        # Mark old SL as CANCELED in DB
        if old_sl_order:
            from src.schemas.order import OrderUpdate
            await self.order_repo.update(old_sl_order, OrderUpdate(status="CANCELED"))

        # 3. Create new SL on Binance
        import time
        import uuid
        new_exchange_sl_id = None
        exit_side = "SELL" if trade.side == "BUY" else "BUY"
        client_sl_id = f"{sl_purpose}_{trade.id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}"

        if self.binance_client:
            try:
                sl_resp = await self.binance_client.create_stop_loss_order(
                    symbol=sym,
                    side=exit_side,
                    stop_price=new_sl_price,
                    qty=trade.remaining_qty,
                    client_order_id=client_sl_id,
                    close_position=False,
                )
                new_exchange_sl_id = str(sl_resp.get("id", ""))
            except Exception:
                pass

        # 4. Save new SL order in DB
        await self.order_repo.create(
            OrderCreate(
                trade_id=trade.id,
                exchange_order_id=new_exchange_sl_id,
                client_order_id=client_sl_id,
                side=exit_side,
                order_type="STOP_MARKET",
                purpose=sl_purpose,
                price=new_sl_price,
                qty=trade.remaining_qty,
                status="NEW",
                close_position=True,
            )
        )

        # 5. Update Trade Record in DB
        await self.trade_repo.update_sl_price(
            trade_id=trade.id,
            new_sl_price=new_sl_price,
        )

        # 6. Log Trade Event
        await self.trade_event_repo.log_event(
            trade_id=trade.id,
            event_type=event_type,
            payload={"new_sl_price": float(new_sl_price)},
        )

    async def finalize_trade_closure(
        self,
        trade_id: int,
        close_reason: str,
        result_type: Optional[str] = None,
        exit_price: Optional[Decimal] = None,
        closed_qty: Optional[Decimal] = None,
    ) -> Any:
        """Finalize closed trade, cancel remaining orders, calculate PnL, and save TradeSummary."""
        trade = await self.trade_repo.get_detail(trade_id)
        if not trade:
            trade = await self.trade_repo.get(trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade {trade_id} not found", trade_id=trade_id)

        sym = trade.instrument.symbol if getattr(trade, "instrument", None) else "BTCUSDT"

        # 1. Cancel all open orders in DB and Binance
        await self.order_repo.cancel_all_open_orders_for_trade(trade_id)
        if self.binance_client:
            try:
                await self.binance_client.cancel_all_orders(symbol=sym)
            except Exception:
                pass

        # 2. Compute aggregate financial performance
        total_comm = await self.execution_repo.get_total_commission_by_trade(trade_id)
        total_realized_pnl = await self.execution_repo.get_total_realized_pnl_by_trade(trade_id)
        net_pnl = total_realized_pnl - total_comm

        # Determine result classification
        if result_type:
            res = result_type
        else:
            if net_pnl > Decimal("0"):
                res = "WIN"
            elif net_pnl < Decimal("0"):
                res = "LOSS"
            else:
                res = "BREAKEVEN"

        # Calculate duration
        now = datetime.now()
        opened_at = trade.opened_at or now
        duration_sec = int((now - opened_at).total_seconds())

        # ROI % calculation
        if trade.entry_price and trade.sl_price and trade.position_size:
            initial_risk = Decimal(str(trade.position_size)) * abs(Decimal(str(trade.entry_price)) - Decimal(str(trade.sl_price)))
        else:
            initial_risk = Decimal("100.0")

        roi = ((net_pnl / initial_risk) * Decimal("100")).quantize(Decimal("0.01")) if initial_risk > 0 else Decimal("0")
        rr = (net_pnl / initial_risk).quantize(Decimal("0.01")) if initial_risk > 0 else Decimal("0")

        # 3. Create TradeSummary
        summary = await self.trade_summary_repo.create(
            TradeSummaryCreate(
                trade_id=trade.id,
                gross_pnl=total_realized_pnl,
                net_pnl=net_pnl,
                commission=total_comm,
                funding=Decimal("0.0"),
                roi=roi,
                rr=rr,
                result=res,
                duration_seconds=duration_sec,
                close_reason=close_reason,
                closed_at=now,
            )
        )

        # 4. Mark Trade as CLOSED
        from src.schemas.trade import TradeStatusUpdate
        await self.trade_repo.update_trade_status(
            trade_id=trade.id,
            schema=TradeStatusUpdate(status="CLOSED", closed_at=now),
        )
        trade.remaining_qty = Decimal("0")
        await self.trade_repo.session.commit()

        # 5. Telegram Notification & Circuit Breaker Check
        if self.telegram_client:
            try:
                if res == "LOSS":
                    price_prec = trade.instrument.price_precision if getattr(trade, "instrument", None) else 4
                    qty_prec = trade.instrument.qty_precision if getattr(trade, "instrument", None) else 2
                    final_exit_price = exit_price if exit_price is not None else trade.sl_price
                    final_closed_qty = closed_qty if closed_qty is not None else trade.position_size
                    await self.telegram_client.send_stop_loss_alert(
                        chat_id="ADMIN_CHANNEL",
                        symbol=sym,
                        side=trade.side,
                        exit_price=final_exit_price,
                        closed_qty=final_closed_qty,
                        realized_pnl=net_pnl,
                        price_precision=price_prec,
                        qty_precision=qty_prec,
                    )
            except Exception:
                pass

        # Circuit Breaker: Auto-pause bot if cumulative daily loss reaches limit
        if res == "LOSS" and self.daily_risk_repo:
            try:
                today_start = datetime(now.year, now.month, now.day)
                perf = await self.trade_summary_repo.get_performance_summary(
                    account_id=trade.account_id,
                    start_date=today_start,
                    end_date=now,
                )
                today_net_pnl = perf.get("total_net_pnl", Decimal("0.0"))
                today_snapshot = await self.daily_risk_repo.get_daily_snapshot(trade.account_id, now.date())
                daily_budget = today_snapshot.risk_amount if today_snapshot else Decimal("20.0")
                max_daily_loss = daily_budget * Decimal("3")  # 3x standard trade risk = 6% loss cap

                if today_net_pnl <= -max_daily_loss:
                    if self.bot_setting_repo:
                        await self.bot_setting_repo.set_value("is_paused", "true")
                        await self.bot_setting_repo.set_value("trading_status", "PAUSED")
                    if self.telegram_client:
                        try:
                            await self.telegram_client.send_message(
                                chat_id="ADMIN_CHANNEL",
                                text=(
                                    f"🚨 <b>DAILY LOSS LIMIT REACHED!</b>\n"
                                    f"━━━━━━━━━━━━━━━━━━━\n"
                                    f"📉 Total Kerugian Hari Ini: <b>${abs(today_net_pnl):,.2f} USDT</b>\n"
                                    f"🛑 Batas Toleransi Harian: <b>${max_daily_loss:,.2f} USDT</b>\n"
                                    f"🔒 Bot otomatis di-<b>PAUSE</b> untuk mengamankan sisa modal.\n"
                                    f"🌅 Bot akan otomatis aktif kembali saat reset harian (00:00 WIB)."
                                ),
                            )
                        except Exception:
                            pass

                    await ws_manager.broadcast(
                        "CIRCUIT_BREAKER_TRIGGERED",
                        {
                            "reason": "Daily loss limit reached",
                            "daily_loss": float(today_net_pnl),
                            "max_limit": float(max_daily_loss),
                        },
                    )
            except Exception:
                pass

        await ws_manager.broadcast(
            "TRADE_CLOSED",
            {
                "trade_id": trade.id,
                "symbol": sym,
                "close_reason": close_reason,
                "result": res,
                "net_pnl": float(net_pnl),
                "roi": float(roi),
            },
        )

        return summary

    async def close_position_market(self, trade_id: int, reason: str = "MANUAL_CLOSE") -> bool:
        """Emergency or manual market close of an open trade.

        Raises:
            TradeNotFoundError: If trade does not exist.
            InvalidTradeStateError: If trade is already CLOSED or CANCELLED.
        """
        trade = await self.trade_repo.get_detail(trade_id)
        if not trade:
            trade = await self.trade_repo.get(trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade with ID {trade_id} was not found.", trade_id=trade_id)

        if trade.status in ("CLOSED", "CANCELLED"):
            raise InvalidTradeStateError(
                f"Trade #{trade_id} cannot be closed because it is already {trade.status}.",
                trade_id=trade_id,
            )

        sym = trade.instrument.symbol if getattr(trade, "instrument", None) else "BTCUSDT"
        exit_side = "SELL" if trade.side == "BUY" else "BUY"

        if self.binance_client and trade.remaining_qty and trade.remaining_qty > Decimal("0"):
            try:
                await self.binance_client.create_entry_order(
                    symbol=sym,
                    side=exit_side,
                    order_type="MARKET",
                    qty=trade.remaining_qty,
                    reduce_only=True,
                )
            except Exception:
                pass

        await self.finalize_trade_closure(trade_id=trade.id, close_reason=reason)
        return True