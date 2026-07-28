"""Data-access layer for trades, risk, orders, executions, events, and summaries."""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import (
    DailyRiskConfig, Trade, TradeRisk, Order,
    Execution, TradeEvent, TradeSummary
)
from src.services.risk_calculator import RiskCalculationResult


class TradeRepository:
    """CRUD operations for trades and related entities (risk, orders, executions, events, summaries)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # 1. DAILY RISK SNAPSHOT
    # ------------------------------------------------------------------

    async def get_daily_risk(self, date_str: str) -> Optional[DailyRiskConfig]:
        """Fetch the daily risk config for a given date (YYYY-MM-DD)."""
        stmt = select(DailyRiskConfig).where(DailyRiskConfig.date == date_str)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_daily_risk_snapshot(
        self, date_str: str, balance: float, risk_percent: float
    ) -> DailyRiskConfig:
        """Persist a daily risk snapshot with the current USDT balance.

        Args:
            date_str: Date string in YYYY-MM-DD format.
            balance: Total USDT balance.
            risk_percent: Percentage of balance allocated per trade.

        Returns:
            The newly created ``DailyRiskConfig`` instance.
        """
        risk_amount = balance * (risk_percent / 100.0)
        snapshot = DailyRiskConfig(
            date=date_str,
            balance=balance,
            risk_percent=risk_percent,
            risk_amount=risk_amount
        )
        self.session.add(snapshot)
        await self.session.commit()
        await self.session.refresh(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # 2. TRADE & TRADE RISK
    # ------------------------------------------------------------------

    async def create_trade_with_risk(
        self,
        signal_id: int,
        symbol: str,
        side: str,
        leverage: int,
        risk_date: str,
        risk_res: RiskCalculationResult,
        tp1_price: Optional[float] = None,
        tp2_price: Optional[float] = None,
        tp3_price: Optional[float] = None,
    ) -> Trade:
        """Create a trade record and its associated risk detail in one transaction.

        Args:
            signal_id: FK to the source signal.
            symbol: Trading pair.
            side: ``BUY`` or ``SELL``.
            leverage: Position leverage.
            risk_date: Date of the daily risk config.
            risk_res: Result from the risk calculator.
            tp1_price / tp2_price / tp3_price: Optional take-profit prices.

        Returns:
            The newly created ``Trade`` instance (with ``trade_risk`` populated).
        """
        trade = Trade(
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            status="WAITING_ENTRY",
            entry_price=risk_res.entry_price,
            sl_price=risk_res.stop_loss_price,
            tp1_price=tp1_price,
            tp2_price=tp2_price,
            tp3_price=tp3_price,
            leverage=leverage,
            margin_mode="ISOLATED",
            position_size=risk_res.position_size,
            remaining_qty=risk_res.position_size
        )
        self.session.add(trade)
        await self.session.flush()

        trade_risk = TradeRisk(
            trade_id=trade.id,
            risk_date=risk_date,
            entry=risk_res.entry_price,
            stop=risk_res.stop_loss_price,
            stop_distance=risk_res.stop_distance,
            qty=risk_res.position_size,
            margin=risk_res.required_margin,
            leverage=leverage
        )
        self.session.add(trade_risk)

        await self.session.commit()
        await self.session.refresh(trade)
        return trade

    async def update_trade_status(
        self, trade_id: int, status: str,
        opened_at: Optional[datetime] = None, closed_at: Optional[datetime] = None
    ) -> None:
        """Update the trade lifecycle status.

        Values: ``WAITING_ENTRY``, ``OPEN``, ``PARTIAL``, ``CLOSED``, ``CANCELLED``.
        """
        values = {"status": status}
        if opened_at is not None:
            values["opened_at"] = opened_at
        if closed_at is not None:
            values["closed_at"] = closed_at

        stmt = update(Trade).where(Trade.id == trade_id).values(**values)
        await self.session.execute(stmt)
        await self.session.commit()

    # ------------------------------------------------------------------
    # 3. ORDERS & EXECUTIONS
    # ------------------------------------------------------------------

    async def create_order(
        self,
        trade_id: int,
        purpose: str,
        order_type: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        binance_order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Order:
        """Persist a new order submitted to Binance.

        Args:
            trade_id: FK to the parent trade.
            purpose: Order role (ENTRY, TP1, SL, etc.).
            order_type: MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET.
            side: BUY or SELL.
            qty: Order quantity.
            price: Limit price (None for market orders).
            binance_order_id: Binance-side order ID.
            client_order_id: Client-generated ID.

        Returns:
            The newly created ``Order`` instance.
        """
        order = Order(
            trade_id=trade_id,
            binance_order_id=binance_order_id,
            client_order_id=client_order_id,
            purpose=purpose,
            type=order_type,
            side=side,
            price=price,
            qty=qty,
            status="NEW"
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def update_order_status(
        self, binance_order_id: str, status: str, filled_qty: Optional[float] = None
    ) -> None:
        """Update an order's status from the Binance WebSocket stream.

        Status values: ``NEW``, ``PARTIALLY_FILLED``, ``FILLED``, ``CANCELED``,
        ``EXPIRED``, ``REJECTED``.
        """
        values = {"status": status}
        if filled_qty is not None:
            values["filled_qty"] = filled_qty

        stmt = update(Order).where(Order.binance_order_id == binance_order_id).values(**values)
        await self.session.execute(stmt)
        await self.session.commit()

    async def record_execution(
        self,
        order_id: int,
        trade_id: int,
        price: float,
        qty: float,
        commission: float = 0.0,
        realized_pnl: float = 0.0
    ) -> Execution:
        """Log a partial or full fill from the Binance user data stream."""
        execution = Execution(
            order_id=order_id,
            trade_id=trade_id,
            price=price,
            qty=qty,
            commission=commission,
            realized_pnl=realized_pnl
        )
        self.session.add(execution)
        await self.session.commit()
        return execution

    # ------------------------------------------------------------------
    # 4. EVENTS & SUMMARY
    # ------------------------------------------------------------------

    async def log_event(self, trade_id: int, event_type: str, payload_json: Optional[str] = None) -> None:
        """Record a trade lifecycle event (SL_MOVED_TO_BEP, TP1, TRAILING_ENABLED, etc.)."""
        event = TradeEvent(trade_id=trade_id, event_type=event_type, payload_json=payload_json)
        self.session.add(event)
        await self.session.commit()

    async def save_summary(
        self,
        trade_id: int,
        gross_pnl: float,
        net_pnl: float,
        commission: float,
        roi: float,
        rr: float,
        win: int,
        duration_seconds: int,
        close_reason: str,
        closed_at: datetime
    ) -> TradeSummary:
        """Persist the performance summary after a trade is closed."""
        summary = TradeSummary(
            trade_id=trade_id,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            commission=commission,
            roi=roi,
            rr=rr,
            win=win,
            duration_seconds=duration_seconds,
            close_reason=close_reason,
            closed_at=closed_at
        )
        self.session.add(summary)
        await self.session.commit()
        return summary

    async def has_active_trade_for_symbol(self, symbol: str, side: Optional[str] = None) -> bool:
        """Check whether an active trade exists for the given symbol and optional side.

        Active statuses: ``WAITING_ENTRY``, ``OPEN``, ``PARTIAL``.
        """
        conditions = [
            Trade.symbol == symbol,
            Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"])
        ]
        if side is not None:
            conditions.append(Trade.side == side)

        stmt = select(Trade).where(*conditions)
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def get_active_trades(self) -> List[Trade]:
        """Return all trades with status ``WAITING_ENTRY``, ``OPEN``, or ``PARTIAL``."""
        stmt = select(Trade).where(Trade.status.in_(["WAITING_ENTRY", "OPEN", "PARTIAL"]))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_performance_summary(self) -> dict:
        """Aggregate performance statistics from the ``trade_summary`` table.

        Returns:
            A dict with keys ``total_trades``, ``winning_trades``,
            ``losing_trades``, ``winrate``, ``total_gross_pnl``,
            ``total_net_pnl``, and ``total_commission``.
        """
        stmt = select(
            func.count(TradeSummary.trade_id).label("total_trades"),
            func.sum(TradeSummary.win).label("winning_trades"),
            func.sum(TradeSummary.gross_pnl).label("total_gross_pnl"),
            func.sum(TradeSummary.net_pnl).label("total_net_pnl"),
            func.sum(TradeSummary.commission).label("total_commission")
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row or not row.total_trades:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "winrate": 0.0, "total_gross_pnl": 0.0, "total_net_pnl": 0.0,
                "total_commission": 0.0
            }

        total = row.total_trades or 0
        win = row.winning_trades or 0
        loss = total - win
        winrate = (win / total * 100.0) if total > 0 else 0.0

        return {
            "total_trades": total,
            "winning_trades": win,
            "losing_trades": loss,
            "winrate": winrate,
            "total_gross_pnl": row.total_gross_pnl or 0.0,
            "total_net_pnl": row.total_net_pnl or 0.0,
            "total_commission": row.total_commission or 0.0
        }

    async def get_expired_waiting_trades(self, max_hours: int = 4) -> List[Trade]:
        """Return trades stuck in ``WAITING_ENTRY`` for longer than ``max_hours``.

        Used by the cron scheduler to clean up orphan limit orders.
        """
        cutoff_time = datetime.now() - timedelta(hours=max_hours)
        stmt = select(Trade).where(
            Trade.status == "WAITING_ENTRY",
            Trade.created_at <= cutoff_time
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())