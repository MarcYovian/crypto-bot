"""Use case for handling order fill execution reports from exchange WebSocket / REST."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.application.dto.trade_commands import OrderFillPayload, PlaceBracketOrdersCommand
from src.application.use_cases.trades.place_bracket_orders_use_case import PlaceBracketOrdersUseCase
from src.domain.events.trade_events import (
    StopLossMovedEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    TradePartiallyClosedEvent,
)
from src.domain.exceptions import TradeNotFoundError
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IExecutionRepository,
    IInstrumentRepository,
    IOrderRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeRiskRepository,
    ITradeSummaryRepository,
)
from src.domain.services.precision_filter import PrecisionFilterDomainService
from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, OrderStatus, OrderType, TradeStatus
from src.presentation.api.schemas import (
    ExecutionCreate,
    OrderCreate,
    OrderUpdate,
    OrderStatusUpdate,
    TradeStatusUpdate,
    TradeRiskCreate,
    TradeSummaryCreate,
)

logger = logging.getLogger(__name__)


class HandleOrderFillUseCase:
    """Orchestrates trade state machine transitions when exchange orders get filled."""

    def __init__(
        self,
        trade_repo: ITradeRepository,
        order_repo: IOrderRepository,
        execution_repo: IExecutionRepository,
        trade_event_repo: ITradeEventRepository,
        trade_risk_repo: Optional[ITradeRiskRepository] = None,
        trade_summary_repo: Optional[ITradeSummaryRepository] = None,
        daily_risk_repo: Optional[IDailyRiskRepository] = None,
        instrument_repo: Optional[IInstrumentRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        event_publisher: Optional[IDomainEventPublisher] = None,
        precision_filter: Optional[PrecisionFilterDomainService] = None,
        risk_calculator: Optional[RiskCalculatorDomainService] = None,
        place_bracket_orders_use_case: Optional[PlaceBracketOrdersUseCase] = None,
    ) -> None:

        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_risk_repo = trade_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.instrument_repo = instrument_repo
        self.exchange_gateway = exchange_gateway
        self.event_publisher = event_publisher
        self.precision = precision_filter or PrecisionFilterDomainService()
        self.risk_calc = risk_calculator or RiskCalculatorDomainService()
        self.place_brackets_use_case = place_bracket_orders_use_case or PlaceBracketOrdersUseCase(
            order_repo=order_repo,
            exchange_gateway=exchange_gateway,
            trade_repo=trade_repo,
            risk_calculator=self.risk_calc,
        )

    async def execute(self, payload: OrderFillPayload) -> Dict[str, Any]:
        """Process an order fill event from exchange."""
        # 1. Resolve matching order in database
        order = None
        if payload.client_order_id is not None and payload.client_order_id != "":
            order = await self.order_repo.get_by_client_order_id(payload.client_order_id)
        if not order and payload.exchange_order_id:
            order = await self.order_repo.get_by_exchange_order_id(payload.exchange_order_id)
        if not order and payload.order_id is not None and isinstance(payload.order_id, int):
            order = await self.order_repo.get(payload.order_id)


        if not order:
            logger.warning(
                "Received fill report for untracked order: ex_id=%s, cl_id=%s",
                payload.exchange_order_id,
                payload.client_order_id,
            )
            return {"status": "UNTRACKED_ORDER", "order_id": payload.exchange_order_id}

        trade = await self.trade_repo.get(order.trade_id)
        if not trade:
            raise TradeNotFoundError(f"Trade #{order.trade_id} not found for filled order #{order.id}")

        # 2. Record Execution fill in DB
        await self.execution_repo.create(
            ExecutionCreate(
                trade_id=trade.id,
                order_id=order.id,
                price=payload.fill_price,
                qty=payload.fill_qty,
                commission=payload.fee,
                commission_asset=payload.fee_asset,
            )
        )

        # 3. Update Order status
        cum_filled = getattr(payload, "cumulative_filled_qty", None)
        if cum_filled is None:
            cum_filled = getattr(payload, "fill_qty", Decimal("0"))

        status_val = str(getattr(payload, "status", "")).upper()
        is_fully_filled = (
            (status_val in ("FILLED", "ORDERSTATUS.FILLED"))
            or (order.qty and cum_filled >= order.qty)
        )
        await self.order_repo.update(
            order,
            OrderUpdate(
                status="FILLED" if is_fully_filled else "PARTIALLY_FILLED",
                filled_qty=cum_filled,
                price=payload.fill_price,
            ),
        )

        purpose_str = order.purpose.value if hasattr(order.purpose, "value") else str(order.purpose or "UNKNOWN")
        purpose = purpose_str.upper()

        # 4. Dispatch based on Order Purpose
        if purpose == "ENTRY":
            return await self._handle_entry_fill(trade, order, payload)
        elif purpose in ("TP1", "TP2", "TP3", "TAKE_PROFIT"):
            return await self._handle_tp_fill(trade, order, payload, tp_tier=purpose)
        elif purpose in ("SL", "STOP_LOSS", "BEP_SL", "TRAILING_SL"):
            return await self._handle_sl_fill(trade, order, payload)
        else:
            logger.info("Processed generic order fill for Trade #%s (Purpose: %s)", trade.id, purpose)
            return {"status": "FILLED", "trade_id": trade.id, "purpose": purpose}

    async def _handle_entry_fill(self, trade: Any, order: Any, payload: OrderFillPayload) -> Dict[str, Any]:
        """Handle LIMIT or MARKET Entry order fill."""
        if trade.status == "WAITING_ENTRY":
            trade = await self.trade_repo.update_entry_fill(
                trade_id=trade.id,
                entry_price=payload.fill_price,
                filled_qty=payload.fill_qty,
            )


            # Record TradeRisk now that order is filled
            if self.daily_risk_repo is not None and self.trade_risk_repo is not None:
                today_risk = await self.daily_risk_repo.get_by_account_id(trade.account_id)
                if today_risk and trade.sl_price:
                    stop_dist = abs(payload.fill_price - trade.sl_price)
                    margin = (trade.position_size * payload.fill_price) / Decimal(str(trade.leverage or 10))
                    await self.trade_risk_repo.create(
                        TradeRiskCreate(
                            trade_id=trade.id,
                            daily_risk_id=today_risk.id,
                            entry=payload.fill_price,
                            stop=trade.sl_price,
                            stop_distance=stop_dist,
                            qty=trade.position_size,
                            margin=margin,
                            risk_amount=margin * Decimal("0.02"),
                            leverage=trade.leverage or 10,
                        )
                    )

            # Place Bracket Orders on exchange
            await self._place_bracket_orders_if_needed(trade, payload.fill_price)

            # Log Trade Event
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type="ENTRY_FILLED",
                payload={"fill_price": float(payload.fill_price), "qty": float(payload.fill_qty)},
            )

            # Publish TradeOpenedEvent
            if self.event_publisher:
                await self.event_publisher.publish(
                    TradeOpenedEvent(
                        trade_id=trade.id,
                        account_id=trade.account_id,
                        symbol=trade.instrument.symbol if trade.instrument else payload.symbol,
                        side=OrderSide(trade.side.upper()),
                        entry_price=payload.fill_price,
                        position_size=trade.position_size,
                        leverage=trade.leverage or 10,
                        sl_price=trade.sl_price,
                        tp1_price=trade.tp1_price,
                        tp2_price=trade.tp2_price,
                        tp3_price=trade.tp3_price,
                    )
                )

        return {"status": "ENTRY_FILLED", "trade_id": trade.id}

    async def _handle_tp_fill(self, trade: Any, order: Any, payload: OrderFillPayload, tp_tier: str) -> Dict[str, Any]:
        """Handle Take-Profit targets (TP1 -> BEP, TP2 -> Trailing SL, TP3 -> Full Close)."""
        new_remaining = max(Decimal("0"), (trade.remaining_qty or trade.position_size) - payload.fill_qty)
        is_fully_closed = (new_remaining <= Decimal("0")) or (tp_tier in ("TP3", "FINAL_TP"))

        # Calculate realized PnL for this tranche
        multiplier = Decimal("1") if trade.side.upper() in ("BUY", "LONG") else Decimal("-1")
        entry_p = trade.entry_price or payload.fill_price
        pnl = (payload.fill_price - entry_p) * payload.fill_qty * multiplier

        if is_fully_closed:
            await self.trade_repo.update_partial_close(
                trade_id=trade.id,
                closed_qty=payload.fill_qty,
            )
            await self.trade_repo.update_trade_status(
                trade_id=trade.id,
                schema=TradeStatusUpdate(status="CLOSED"),
            )

            # Cancel all remaining open orders
            if self.exchange_gateway:
                sym = trade.instrument.symbol if trade.instrument else payload.symbol
                try:
                    await self.exchange_gateway.cancel_all_open_orders(sym)
                except Exception as exc:
                    logger.warning("Failed to cancel open orders on full TP close: %s", exc)

            if self.order_repo:
                try:
                    await self.order_repo.cancel_all_open_orders_for_trade(trade.id)
                except Exception as exc:
                    logger.debug("Failed updating local DB open orders to cancelled: %s", exc)

            # Record Trade Summary
            now = datetime.now()
            tot_comm = await self.execution_repo.get_total_commission_by_trade(trade.id) if hasattr(self.execution_repo, "get_total_commission_by_trade") else Decimal("0.0")
            all_execs = await self.execution_repo.get_executions_by_trade_id(trade.id) if hasattr(self.execution_repo, "get_executions_by_trade_id") else []
            
            entry_p = trade.entry_price or payload.fill_price
            mult = Decimal("1") if trade.side.upper() in ("BUY", "LONG") else Decimal("-1")
            
            # Sum exit PnLs if executions exist
            total_gross = Decimal("0.0")
            for e in all_execs:
                if e.price != entry_p:
                    total_gross += (e.price - entry_p) * e.qty * mult
            if total_gross == Decimal("0.0"):
                total_gross = pnl
            
            final_net = total_gross - tot_comm
            
            if self.trade_summary_repo is not None:
                existing_sum = await self.trade_summary_repo.get(trade.id)
                sum_payload = TradeSummaryCreate(
                    trade_id=trade.id,
                    gross_pnl=total_gross,
                    net_pnl=final_net,
                    commission=tot_comm,
                    funding=Decimal("0.0"),
                    roi=Decimal("0.0"),
                    rr=Decimal("0.0"),
                    result="WIN" if final_net > Decimal("0") else ("LOSS" if final_net < Decimal("0") else "BREAKEVEN"),
                    duration_seconds=0,
                    close_reason="TAKE_PROFIT_COMPLETE",
                    closed_at=now,
                )
                if existing_sum:
                    await self.trade_summary_repo.update(existing_sum, sum_payload)
                else:
                    await self.trade_summary_repo.create(sum_payload)


            if self.event_publisher:
                await self.event_publisher.publish(
                    TradeClosedEvent(
                        trade_id=trade.id,
                        account_id=trade.account_id,
                        symbol=trade.instrument.symbol if trade.instrument else payload.symbol,
                        side=OrderSide(trade.side.upper()),
                        exit_price=payload.fill_price,
                        closed_qty=trade.position_size,
                        total_realized_pnl=pnl,
                        close_reason="TAKE_PROFIT_ALL",
                    )
                )
        else:
            # TP1 or TP2 Partial Fill -> Shift SL to BEP or Trailing SL
            await self.trade_repo.update_partial_close(
                trade_id=trade.id,
                closed_qty=payload.fill_qty,
                remaining_qty=new_remaining,
                realized_pnl=pnl,
            )

            # Log TP hit event
            await self.trade_event_repo.log_event(
                trade_id=trade.id,
                event_type=f"{tp_tier}_HIT" if tp_tier in ("TP1", "TP2", "TP3") else "TP1_HIT",
                payload={"fill_price": float(payload.fill_price), "qty": float(payload.fill_qty), "pnl": float(pnl)},
            )

            # If TP1 hit -> Shift Stop Loss to BEP (Entry Price)
            if tp_tier == "TP1" and trade.entry_price:
                await self.trade_repo.update_sl_price(trade.id, trade.entry_price)
                await self.trade_event_repo.log_event(
                    trade_id=trade.id,
                    event_type="SL_MOVED_TO_BEP",
                    payload={"new_sl": float(trade.entry_price)},
                )
                await self._shift_stop_loss_to_bep(trade)
            elif tp_tier == "TP2":
                tp1_orders = await self.order_repo.get_orders_by_purpose(trade.id, "TP1")
                tp1_price = tp1_orders[0].price if tp1_orders and tp1_orders[0].price else trade.entry_price
                if tp1_price:
                    await self.trade_repo.update_sl_price(trade.id, tp1_price)
                    await self.trade_event_repo.log_event(
                        trade_id=trade.id,
                        event_type="TRAILING_SL_UPDATED",
                        payload={"new_sl": float(tp1_price)},
                    )

            if self.event_publisher:
                await self.event_publisher.publish(
                    TradePartiallyClosedEvent(
                        trade_id=trade.id,
                        account_id=trade.account_id,
                        symbol=trade.instrument.symbol if trade.instrument else payload.symbol,
                        target_hit=OrderPurpose.from_str(tp_tier),
                        fill_price=payload.fill_price,
                        closed_qty=payload.fill_qty,
                        remaining_qty=new_remaining,
                        realized_pnl=pnl,
                        new_sl_price=trade.entry_price if tp_tier == "TP1" else None,
                    )
                )

        return {"status": "TP_FILLED", "trade_id": trade.id, "tp_tier": tp_tier, "pnl": float(pnl)}

    async def _handle_sl_fill(self, trade: Any, order: Any, payload: OrderFillPayload) -> Dict[str, Any]:
        """Handle Stop-Loss execution (Trade fully stopped out)."""
        entry_p = trade.entry_price or payload.fill_price
        multiplier = Decimal("1") if trade.side.upper() in ("BUY", "LONG") else Decimal("-1")
        loss = (payload.fill_price - entry_p) * payload.fill_qty * multiplier
        fee = payload.fee if payload.fee is not None else Decimal("0.0")
        realized_pnl: Decimal = payload.realized_pnl if payload.realized_pnl is not None else loss
        net_loss: Decimal = realized_pnl - fee

        await self.trade_repo.update_partial_close(
            trade_id=trade.id,
            closed_qty=trade.remaining_qty or payload.fill_qty,
        )
        await self.trade_repo.update_trade_status(
            trade_id=trade.id,
            schema=TradeStatusUpdate(status="CLOSED"),
        )


        # Cancel remaining TP orders
        if self.exchange_gateway:
            sym = trade.instrument.symbol if trade.instrument else payload.symbol
            try:
                await self.exchange_gateway.cancel_all_open_orders(sym)
            except Exception as exc:
                logger.warning("Failed to cancel open orders on SL hit: %s", exc)

        if self.order_repo:
            try:
                await self.order_repo.cancel_all_open_orders_for_trade(trade.id)
            except Exception as exc:
                logger.debug("Failed updating local DB open orders to cancelled: %s", exc)

        # Record Trade Summary
        now = datetime.now()
        tot_comm = await self.execution_repo.get_total_commission_by_trade(trade.id) if hasattr(self.execution_repo, "get_total_commission_by_trade") else fee
        if tot_comm == Decimal("0.0"):
            tot_comm = fee
        net_loss = realized_pnl - tot_comm

        if self.trade_summary_repo is not None:
            existing_sum = await self.trade_summary_repo.get(trade.id)
            sum_payload = TradeSummaryCreate(
                trade_id=trade.id,
                gross_pnl=realized_pnl,
                net_pnl=net_loss,
                commission=tot_comm,
                funding=Decimal("0.0"),
                roi=Decimal("0.0"),
                rr=Decimal("0.0"),
                result="WIN" if net_loss > Decimal("0") else ("LOSS" if net_loss < Decimal("0") else "BREAKEVEN"),
                duration_seconds=0,
                close_reason="SL_HIT",
                closed_at=now,
            )
            if existing_sum:
                await self.trade_summary_repo.update(existing_sum, sum_payload)
            else:
                await self.trade_summary_repo.create(sum_payload)




        if self.event_publisher:
            await self.event_publisher.publish(
                TradeClosedEvent(
                    trade_id=trade.id,
                    account_id=trade.account_id,
                    symbol=trade.instrument.symbol if trade.instrument else payload.symbol,
                    side=OrderSide(trade.side.upper()),
                    exit_price=payload.fill_price,
                    closed_qty=trade.position_size,
                    total_realized_pnl=loss,
                    close_reason="STOP_LOSS_HIT",
                )
            )

        return {"status": "SL_FILLED", "trade_id": trade.id, "pnl": float(loss)}

    async def _place_bracket_orders_if_needed(self, trade: Any, entry_price: Decimal) -> None:
        """Place TP1, TP2, TP3 limits and SL stop-market on exchange."""
        if not self.exchange_gateway or not self.place_brackets_use_case:
            return

        sym = trade.instrument.symbol if trade.instrument else "BTCUSDT"
        bracket_cmd = PlaceBracketOrdersCommand(
            trade_id=trade.id,
            symbol=sym,
            side=trade.side,
            position_size=trade.position_size,
            sl_price=trade.sl_price,
            tp1_price=trade.tp1_price,
            tp2_price=getattr(trade, "tp2_price", None),
            tp3_price=getattr(trade, "tp3_price", None),
            auto_tp_sl=True,
            is_emergency_close_on_sl_fail=False,
        )
        try:
            await self.place_brackets_use_case.execute(bracket_cmd)
        except Exception as exc:
            logger.error("Failed to place bracket orders for trade %s: %s", trade.id, exc)


    async def _shift_stop_loss_to_bep(self, trade: Any) -> None:
        """Cancel current SL and place new BEP SL order at entry price atomically."""
        if not self.exchange_gateway or not trade.entry_price:
            return

        sym = trade.instrument.symbol if trade.instrument else "BTCUSDT"
        is_long = trade.side.upper() in ("BUY", "LONG")
        exit_side = OrderSide.SELL if is_long else OrderSide.BUY

        try:
            # 1. First, check if we can edit existing SL order in-place
            sl_orders = (
                await self.order_repo.get_orders_by_purpose(trade.id, "STOP_LOSS")
                or await self.order_repo.get_orders_by_purpose(trade.id, "SL")
                or await self.order_repo.get_orders_by_purpose(trade.id, "BEP_SL")
            )
            edited = False
            old_sl = sl_orders[0] if sl_orders else None

            if old_sl and old_sl.exchange_order_id and hasattr(self.exchange_gateway, "edit_order"):
                try:
                    edit_resp = await self.exchange_gateway.edit_order(
                        order_id=old_sl.exchange_order_id,
                        symbol=sym,
                        side=exit_side,
                        order_type=OrderType.STOP_MARKET,
                        stop_price=trade.entry_price,
                        qty=trade.remaining_qty or trade.position_size,
                    )
                    edited = True
                    logger.info("Successfully edited Stop Loss in-place to BEP for Trade #%s (New SL: %s)", trade.id, trade.entry_price)
                except Exception as edit_exc:
                    logger.debug("In-place edit_order failed, falling back to safe cancel-and-create: %s", edit_exc)

            if not edited:
                # 2. Cancel existing stop orders on Binance safely
                if old_sl and old_sl.exchange_order_id:
                    try:
                        await self.exchange_gateway.cancel_order(
                            symbol=sym,
                            exchange_order_id=old_sl.exchange_order_id,
                        )
                    except Exception:
                        pass

                # Also clean up any lingering stop orders on exchange to prevent -4130
                if hasattr(self.exchange_gateway, "cancel_stop_orders"):
                    try:
                        await self.exchange_gateway.cancel_stop_orders(sym)
                    except Exception:
                        pass

                if old_sl:
                    await self.order_repo.update(old_sl, OrderUpdate(status="CANCELED"))

                # 3. Place new BEP SL order
                new_sl_resp = await self.exchange_gateway.create_stop_loss_order(
                    symbol=sym,
                    side=exit_side.value,
                    stop_price=trade.entry_price,
                    qty=trade.remaining_qty or trade.position_size,
                    client_order_id=f"BEP_SL_{trade.id}",
                )
                await self.order_repo.create(
                    OrderCreate(
                        trade_id=trade.id,
                        exchange_order_id=new_sl_resp.get("exchange_order_id") or str(new_sl_resp.get("id", "")),
                        client_order_id=f"BEP_SL_{trade.id}",
                        order_type="STOP_MARKET",
                        purpose="BEP_SL",
                        side=exit_side.value,
                        price=trade.entry_price,
                        qty=trade.remaining_qty or trade.position_size,
                        status="NEW",
                    )
                )

            # 4. Update trade stop loss in DB
            await self.trade_repo.update_stop_loss(trade.id, trade.entry_price)

            if self.event_publisher:
                await self.event_publisher.publish(
                    StopLossMovedEvent(
                        trade_id=trade.id,
                        account_id=trade.account_id,
                        symbol=sym,
                        side=OrderSide.from_str(trade.side, default=OrderSide.BUY),
                        old_sl_price=trade.sl_price or trade.entry_price,
                        new_sl_price=trade.entry_price,
                        reason="BEP_AFTER_TP1",
                    )
                )
        except Exception as exc:
            logger.error("Failed shifting Stop Loss to BEP for Trade #%s: %s", trade.id, exc)

    async def execute_from_raw_event(self, order_data: Any) -> Optional[Any]:
        """Parse raw exchange order update, match with DB order via 3-Tier Hierarchy, and execute fill transitions."""
        from src.utils.ws_cache_logger import write_ws_order_cache
        try:
            await write_ws_order_cache(order_data)
        except Exception:
            pass

        if not isinstance(order_data, dict):
            return None

        binance_order_id = str(order_data.get("id") or order_data.get("orderId") or "")
        client_order_id = str(order_data.get("clientOrderId") or "")
        status = str(order_data.get("status") or "").upper()

        if status not in ("CLOSED", "FILLED") or not (binance_order_id or client_order_id):
            return None

        order = None
        # Tier 1: Match by Binance exchange order ID
        if binance_order_id:
            order = await self.order_repo.get_by_exchange_order_id(binance_order_id)

        # Tier 2: Match by client order ID
        if not order and client_order_id:
            order = await self.order_repo.get_by_client_order_id(client_order_id)

        # Tier 3: Contextual Active Trade Resolution (For Binance-generated trigger order IDs e.g. autoclose / market SL executions)
        if not order:
            raw_sym = str(order_data.get("symbol") or "")
            clean_sym = raw_sym.replace("/", "").replace(":USDT", "").upper() or "BTCUSDT"
            active_trades = await self.trade_repo.get_all_active_trades()
            matching_trade = next(
                (t for t in active_trades if (t.instrument and t.instrument.symbol == clean_sym) or (getattr(t, "symbol", "") == clean_sym)),
                None
            )

            if matching_trade:
                trade_side_upper = matching_trade.side.upper()
                order_side_raw = str(order_data.get("side") or "").upper()
                is_exit_side = (
                    (trade_side_upper in ("BUY", "LONG") and order_side_raw in ("SELL", "SHORT"))
                    or (trade_side_upper in ("SELL", "SHORT") and order_side_raw in ("BUY", "LONG"))
                )

                if is_exit_side:
                    fill_p = Decimal(str(order_data.get("average") or order_data.get("price") or 0))
                    qty_f = Decimal(str(order_data.get("filled") or order_data.get("amount") or 0))

                    # Determine resolved purpose (SL vs TP1 vs TP2 vs TP3)
                    resolved_purpose = OrderPurpose.SL
                    if matching_trade.sl_price and fill_p > 0:
                        is_sl_hit = (
                            (trade_side_upper in ("BUY", "LONG") and fill_p <= matching_trade.sl_price * Decimal("1.005"))
                            or (trade_side_upper in ("SELL", "SHORT") and fill_p >= matching_trade.sl_price * Decimal("0.995"))
                        )
                        if is_sl_hit:
                            resolved_purpose = OrderPurpose.SL
                        elif matching_trade.tp1_price and abs(fill_p - matching_trade.tp1_price) < abs(fill_p - matching_trade.sl_price):
                            resolved_purpose = OrderPurpose.TP1
                        elif matching_trade.tp2_price and abs(fill_p - matching_trade.tp2_price) < abs(fill_p - matching_trade.sl_price):
                            resolved_purpose = OrderPurpose.TP2
                        elif matching_trade.tp3_price and abs(fill_p - matching_trade.tp3_price) < abs(fill_p - matching_trade.sl_price):
                            resolved_purpose = OrderPurpose.TP3

                    existing_purpose_orders = await self.order_repo.get_orders_by_purpose(
                        matching_trade.id, resolved_purpose.value if hasattr(resolved_purpose, "value") else str(resolved_purpose)
                    )
                    if existing_purpose_orders:
                        order = existing_purpose_orders[0]
                    else:
                        order = await self.order_repo.create(
                            OrderCreate(
                                trade_id=matching_trade.id,
                                exchange_order_id=binance_order_id,
                                client_order_id=client_order_id or f"EXEC_{matching_trade.id}_{binance_order_id}",
                                order_type="STOP_MARKET" if resolved_purpose == OrderPurpose.SL else "TAKE_PROFIT_MARKET",
                                purpose=resolved_purpose.value,
                                side=order_side_raw,
                                price=fill_p,
                                qty=qty_f or matching_trade.remaining_qty or matching_trade.position_size,
                                status="NEW",
                            )
                        )
                    logger.info(
                        "[WS Stream Tier-3 Match] Matched untracked order %s to Trade #%s (%s) as %s",
                        binance_order_id, matching_trade.id, clean_sym, resolved_purpose
                    )

        if not order:
            logger.debug("[WS Stream] Order %s (%s) not found in DB. Skipping.", client_order_id, binance_order_id)
            return None

        filled_qty = Decimal(str(order_data.get("filled") or order_data.get("amount") or order.qty))
        avg_price = Decimal(str(order_data.get("average") or order_data.get("price") or order.price or 0))
        fee_dict = order_data.get("fee") or {}
        fee_cost = Decimal(str(fee_dict.get("cost") or 0.0)) if isinstance(fee_dict, dict) else Decimal("0.0")

        raw_sym = str(order_data.get("symbol") or "")
        clean_sym = raw_sym.replace("/", "").replace(":USDT", "").upper() or "BTCUSDT"

        side_val = order.side.value if hasattr(order.side, "value") else str(order.side)
        purpose_val = order.purpose.value if hasattr(order.purpose, "value") else str(order.purpose)

        side_enum = OrderSide.from_str(side_val, default=OrderSide.BUY)
        purpose_enum = OrderPurpose.from_str(purpose_val) if purpose_val else None
        order_type_enum = OrderType.MARKET

        fill_payload = OrderFillPayload(
            symbol=clean_sym,
            exchange_order_id=binance_order_id,
            client_order_id=client_order_id or order.client_order_id,
            side=side_enum,
            order_type=order_type_enum,
            status=OrderStatus.FILLED,
            fill_price=avg_price,
            fill_qty=filled_qty,
            cumulative_filled_qty=filled_qty,
            fee=fee_cost,
            fee_asset="USDT",
            trade_id=order.trade_id,
            order_id=order.id,
            purpose=purpose_enum,
        )
        return await self.execute(fill_payload)
