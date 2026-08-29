"""Trade Aggregate Root encapsulating Trade, Orders, Risk, and lifecycle state invariants."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.domain.aggregates.order_aggregate import OrderAggregate
from src.domain.aggregates.trade_state_machine import TradeStateMachine
from src.domain.events.base import DomainEvent
from src.domain.events.trade_events import (
    StopLossMovedEvent,
    TradeCancelledEvent,
    TradeClosedEvent,
    TradeOpenedEvent,
    TradePartiallyClosedEvent,
    TradeWaitingEntryEvent,
)
from src.domain.exceptions.risk import StopLossCannotExceedEntryError
from src.domain.exceptions.trade import InvalidTradeStateError
from src.domain.value_objects.side import MarginMode, OrderSide
from src.domain.value_objects.trade_status import OrderPurpose, TradeStatus

logger = logging.getLogger(__name__)


@dataclass
class TradeAggregate:
    """Aggregate Root for Trade management and business invariant enforcement."""

    account_id: int
    symbol: str
    side: OrderSide
    entry_price: Decimal
    sl_price: Decimal
    position_size: Decimal
    leverage: int
    remaining_qty: Decimal
    status: TradeStatus = TradeStatus.WAITING_ENTRY
    tp_targets: List[Decimal] = field(default_factory=list)
    tp_allocations: List[Any] = field(default_factory=list)
    margin_mode: MarginMode = MarginMode.ISOLATED
    margin_used: Decimal = field(default_factory=lambda: Decimal("0"))
    risk_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    unrealized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    close_reason: Optional[str] = None
    instrument_id: Optional[int] = None
    strategy_id: Optional[int] = None
    signal_id: Optional[int] = None
    created_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    id: Optional[int] = None
    orders: List[OrderAggregate] = field(default_factory=list)
    _uncommitted_events: List[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.side, str):
            self.side = OrderSide.from_str(self.side)
        if isinstance(self.status, str):
            self.status = TradeStatus.from_str(self.status)
        if isinstance(self.margin_mode, str):
            self.margin_mode = MarginMode.from_str(self.margin_mode)

        self.entry_price = Decimal(str(self.entry_price))
        self.sl_price = Decimal(str(self.sl_price))
        self.position_size = Decimal(str(self.position_size))
        self.remaining_qty = Decimal(str(self.remaining_qty))
        self.risk_amount = Decimal(str(self.risk_amount))
        self.realized_pnl = Decimal(str(self.realized_pnl))

        if self.created_at is None:
            self.created_at = datetime.now()

    # =========================================================================
    # FACTORIES
    # =========================================================================

    @classmethod
    def create_pending(
        cls,
        account_id: int,
        symbol: str,
        side: Union[OrderSide, str],
        target_entry_price: Union[Decimal, float],
        sl_price: Union[Decimal, float],
        position_size: Union[Decimal, float],
        leverage: int,
        tp_targets: Optional[List[Union[Decimal, float]]] = None,
        tp_allocations: Optional[List[Any]] = None,
        margin_mode: Union[MarginMode, str] = MarginMode.ISOLATED,
        instrument_id: Optional[int] = None,
        strategy_id: Optional[int] = None,
        signal_id: Optional[int] = None,
        risk_amount: Optional[Decimal] = None,
        margin_used: Optional[Decimal] = None,
        trade_id: Optional[int] = None,
    ) -> "TradeAggregate":
        """Factory creating a new Trade Aggregate in WAITING_ENTRY status."""
        entry_dec = Decimal(str(target_entry_price))
        sl_dec = Decimal(str(sl_price))
        size_dec = Decimal(str(position_size))
        side_vo = OrderSide.from_str(side) if isinstance(side, str) else side
        tp_decs = [Decimal(str(tp)) for tp in (tp_targets or [])]

        calc_risk = risk_amount if risk_amount is not None else (abs(entry_dec - sl_dec) * size_dec)
        calc_margin = margin_used if margin_used is not None else ((entry_dec * size_dec) / Decimal(str(leverage or 10)))

        agg = cls(
            id=trade_id,
            account_id=account_id,
            symbol=symbol.upper(),
            side=side_vo,
            entry_price=entry_dec,
            sl_price=sl_dec,
            position_size=size_dec,
            remaining_qty=size_dec,
            leverage=leverage,
            status=TradeStatus.WAITING_ENTRY,
            tp_targets=tp_decs,
            tp_allocations=tp_allocations or [],
            margin_mode=MarginMode.from_str(margin_mode) if isinstance(margin_mode, str) else margin_mode,
            margin_used=calc_margin,
            risk_amount=calc_risk,
            instrument_id=instrument_id,
            strategy_id=strategy_id,
            signal_id=signal_id,
        )

        agg.record_event(
            TradeWaitingEntryEvent(
                trade_id=trade_id or 0,
                account_id=account_id,
                symbol=symbol.upper(),
                side=side_vo,
                target_entry_price=entry_dec,
                position_size=size_dec,
                leverage=leverage,
                sl_price=sl_dec,
                tp1_price=tp_decs[0] if len(tp_decs) > 0 else None,
                tp2_price=tp_decs[1] if len(tp_decs) > 1 else None,
                tp3_price=tp_decs[2] if len(tp_decs) > 2 else None,
                margin_mode=agg.margin_mode,
                strategy_id=strategy_id,
                signal_id=signal_id,
            )
        )
        return agg

    @classmethod
    def create_open(
        cls,
        account_id: int,
        symbol: str,
        side: Union[OrderSide, str],
        entry_price: Union[Decimal, float],
        sl_price: Union[Decimal, float],
        position_size: Union[Decimal, float],
        leverage: int,
        tp_targets: Optional[List[Union[Decimal, float]]] = None,
        tp_allocations: Optional[List[Any]] = None,
        margin_mode: Union[MarginMode, str] = MarginMode.ISOLATED,
        instrument_id: Optional[int] = None,
        strategy_id: Optional[int] = None,
        signal_id: Optional[int] = None,
        risk_amount: Optional[Decimal] = None,
        margin_used: Optional[Decimal] = None,
        trade_id: Optional[int] = None,
        opened_at: Optional[datetime] = None,
    ) -> "TradeAggregate":
        """Factory creating an immediately OPEN Trade Aggregate (e.g. Market entry)."""
        entry_dec = Decimal(str(entry_price))
        sl_dec = Decimal(str(sl_price))
        size_dec = Decimal(str(position_size))
        side_vo = OrderSide.from_str(side) if isinstance(side, str) else side
        tp_decs = [Decimal(str(tp)) for tp in (tp_targets or [])]

        calc_risk = risk_amount if risk_amount is not None else (abs(entry_dec - sl_dec) * size_dec)
        calc_margin = margin_used if margin_used is not None else ((entry_dec * size_dec) / Decimal(str(leverage or 10)))
        open_time = opened_at or datetime.now()

        agg = cls(
            id=trade_id,
            account_id=account_id,
            symbol=symbol.upper(),
            side=side_vo,
            entry_price=entry_dec,
            sl_price=sl_dec,
            position_size=size_dec,
            remaining_qty=size_dec,
            leverage=leverage,
            status=TradeStatus.OPEN,
            tp_targets=tp_decs,
            tp_allocations=tp_allocations or [],
            margin_mode=MarginMode.from_str(margin_mode) if isinstance(margin_mode, str) else margin_mode,
            margin_used=calc_margin,
            risk_amount=calc_risk,
            instrument_id=instrument_id,
            strategy_id=strategy_id,
            signal_id=signal_id,
            opened_at=open_time,
        )

        agg.record_event(
            TradeOpenedEvent(
                trade_id=trade_id or 0,
                account_id=account_id,
                symbol=symbol.upper(),
                side=side_vo,
                entry_price=entry_dec,
                position_size=size_dec,
                leverage=leverage,
                sl_price=sl_dec,
                tp1_price=tp_decs[0] if len(tp_decs) > 0 else None,
                tp2_price=tp_decs[1] if len(tp_decs) > 1 else None,
                tp3_price=tp_decs[2] if len(tp_decs) > 2 else None,
                margin_mode=agg.margin_mode,
                strategy_id=strategy_id,
                signal_id=signal_id,
            )
        )
        return agg

    # =========================================================================
    # DOMAIN LIFECYCLE METHODS & MUTATIONS
    # =========================================================================

    def execute_entry(
        self,
        fill_price: Union[Decimal, float],
        fill_qty: Union[Decimal, float],
        opened_at: Optional[datetime] = None,
        exchange_order_id: Optional[str] = None,
    ) -> None:
        """Transition trade from WAITING_ENTRY to OPEN upon limit fill."""
        TradeStateMachine.validate_transition(self.status, TradeStatus.OPEN, self.id)

        self.entry_price = Decimal(str(fill_price))
        self.position_size = Decimal(str(fill_qty))
        self.remaining_qty = Decimal(str(fill_qty))
        self.status = TradeStatus.OPEN
        self.opened_at = opened_at or datetime.now()

        # Update entry order if exists
        for order in self.orders:
            if order.purpose == OrderPurpose.ENTRY and order.is_active:
                order.mark_filled(fill_price=self.entry_price, fill_qty=self.position_size, filled_at=self.opened_at)
                if exchange_order_id:
                    order.exchange_order_id = exchange_order_id

        self.record_event(
            TradeOpenedEvent(
                trade_id=self.id or 0,
                account_id=self.account_id,
                symbol=self.symbol,
                side=self.side,
                entry_price=self.entry_price,
                position_size=self.position_size,
                leverage=self.leverage,
                sl_price=self.sl_price,
                tp1_price=self.tp_targets[0] if len(self.tp_targets) > 0 else None,
                tp2_price=self.tp_targets[1] if len(self.tp_targets) > 1 else None,
                tp3_price=self.tp_targets[2] if len(self.tp_targets) > 2 else None,
                margin_mode=self.margin_mode,
                strategy_id=self.strategy_id,
                signal_id=self.signal_id,
            )
        )

    def apply_partial_fill(
        self,
        tp_tier: Union[str, OrderPurpose],
        fill_price: Union[Decimal, float],
        fill_qty: Union[Decimal, float],
        new_sl_price: Optional[Union[Decimal, float]] = None,
    ) -> Decimal:
        """Record a partial Take Profit fill and update remaining position size & PnL."""
        TradeStateMachine.validate_transition(self.status, TradeStatus.PARTIAL, self.id)

        qty_dec = Decimal(str(fill_qty))
        price_dec = Decimal(str(fill_price))

        if qty_dec > self.remaining_qty:
            qty_dec = self.remaining_qty

        # Calculate tranche realized PnL
        if self.side.is_buy:
            tranche_pnl = (price_dec - self.entry_price) * qty_dec
        else:
            tranche_pnl = (self.entry_price - price_dec) * qty_dec

        self.remaining_qty -= qty_dec
        self.realized_pnl += tranche_pnl
        self.status = TradeStatus.PARTIAL

        # If new SL is supplied (e.g. BEP on TP1), apply it safely
        sl_dec: Optional[Decimal] = None
        if new_sl_price is not None:
            sl_dec = Decimal(str(new_sl_price))
            self.sl_price = sl_dec

        purpose_vo = OrderPurpose.from_str(tp_tier) if isinstance(tp_tier, str) else tp_tier

        # Update matching TP order in aggregate
        for order in self.orders:
            if order.purpose == purpose_vo and order.is_active:
                order.mark_filled(fill_price=price_dec, fill_qty=qty_dec)

        self.record_event(
            TradePartiallyClosedEvent(
                trade_id=self.id or 0,
                account_id=self.account_id,
                symbol=self.symbol,
                target_hit=purpose_vo,
                fill_price=price_dec,
                closed_qty=qty_dec,
                remaining_qty=self.remaining_qty,
                realized_pnl=tranche_pnl,
                new_sl_price=sl_dec,
                side=self.side,
            )
        )
        return tranche_pnl

    def shift_stop_loss(self, new_sl_price: Union[Decimal, float], reason: str) -> None:
        """Safely move stop loss (e.g. to BEP or trailing target).
        
        Enforces invariant: New SL cannot worsen loss risk.
        """
        new_sl_dec = Decimal(str(new_sl_price))
        old_sl = self.sl_price

        # Invariant checks:
        if self.side.is_buy:
            if new_sl_dec < self.sl_price:
                raise StopLossCannotExceedEntryError(
                    f"Cannot move BUY Stop Loss lower from {old_sl} to {new_sl_dec} (would increase risk)."
                )
        else:
            if new_sl_dec > self.sl_price:
                raise StopLossCannotExceedEntryError(
                    f"Cannot move SELL Stop Loss higher from {old_sl} to {new_sl_dec} (would increase risk)."
                )

        self.sl_price = new_sl_dec
        self.record_event(
            StopLossMovedEvent(
                trade_id=self.id or 0,
                account_id=self.account_id,
                symbol=self.symbol,
                old_sl_price=old_sl,
                new_sl_price=new_sl_dec,
                reason=reason,
                side=self.side,
            )
        )

    def close(
        self,
        exit_price: Union[Decimal, float],
        close_reason: str,
        closed_qty: Optional[Union[Decimal, float]] = None,
        closed_at: Optional[datetime] = None,
    ) -> Decimal:
        """Completely exit position, transition to CLOSED status, and compute final realized PnL."""
        TradeStateMachine.validate_transition(self.status, TradeStatus.CLOSED, self.id)

        exit_dec = Decimal(str(exit_price))
        qty_to_close = Decimal(str(closed_qty)) if closed_qty is not None else self.remaining_qty

        if qty_to_close > self.remaining_qty:
            qty_to_close = self.remaining_qty

        # Calculate final tranche PnL
        if self.side.is_buy:
            final_pnl = (exit_dec - self.entry_price) * qty_to_close
        else:
            final_pnl = (self.entry_price - exit_dec) * qty_to_close

        self.realized_pnl += final_pnl
        self.remaining_qty = Decimal("0")
        self.status = TradeStatus.CLOSED
        self.close_reason = close_reason
        self.closed_at = closed_at or datetime.now()

        # Mark any remaining active orders as filled/cancelled
        for order in self.orders:
            if order.is_active:
                if "STOP" in close_reason.upper() and order.purpose == OrderPurpose.STOP_LOSS:
                    order.mark_filled(fill_price=exit_dec, fill_qty=qty_to_close, filled_at=self.closed_at)
                else:
                    order.mark_cancelled()

        self.record_event(
            TradeClosedEvent(
                trade_id=self.id or 0,
                account_id=self.account_id,
                symbol=self.symbol,
                exit_price=exit_dec,
                total_realized_pnl=self.realized_pnl,
                close_reason=close_reason,
                closed_qty=qty_to_close,
                side=self.side,
                status=TradeStatus.CLOSED,
            )
        )
        return final_pnl

    def cancel(self, reason: str = "CANCELLED_BY_OPERATOR") -> None:
        """Cancel an unfilled waiting trade."""
        TradeStateMachine.validate_transition(self.status, TradeStatus.CANCELLED, self.id)

        self.status = TradeStatus.CANCELLED
        self.close_reason = reason
        self.closed_at = datetime.now()

        for order in self.orders:
            if order.is_active:
                order.mark_cancelled()

        self.record_event(
            TradeCancelledEvent(
                trade_id=self.id or 0,
                account_id=self.account_id,
                symbol=self.symbol,
                reason=reason,
                status=TradeStatus.CANCELLED,
            )
        )

    def add_order(self, order: OrderAggregate) -> None:
        """Attach a child order entity to this trade aggregate."""
        if self.id is not None:
            order.trade_id = self.id
        self.orders.append(order)

    def record_event(self, event: DomainEvent) -> None:
        """Record an uncommitted domain event inside the aggregate."""
        self._uncommitted_events.append(event)

    def collect_events(self) -> List[DomainEvent]:
        """Collect and clear all uncommitted domain events for publication."""
        events = list(self._uncommitted_events)
        self._uncommitted_events.clear()
        return events
