"""Execution ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.orders import Order
    from src.database.models.trades import Trade


class Execution(Base):
    """A filled execution (partial or full) from an exchange.

    Attributes:
        id: Auto-increment primary key.
        order_id: FK to the parent order.
        trade_id: FK to the parent trade.
        price: Fill price.
        qty: Filled quantity (this execution).
        commission: Fee paid for this fill.
        commission_asset: Asset used for fee payment.
        realized_pnl: Realised PnL for this fill (if closing).
        is_maker: Flag indicating if the fill was a maker order.
        executed_at: Fill timestamp.
    """

    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    commission_asset: Mapped[str] = mapped_column(Text, server_default="USDT")
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    is_maker: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="FALSE")

    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    order: Mapped["Order"] = relationship(back_populates="executions")
    trade: Mapped["Trade"] = relationship(back_populates="executions")

    __table_args__ = (
        Index("idx_executions_order_id", "order_id"),
        Index("idx_executions_trade_id", "trade_id"),
        Index("idx_executions_trade_time", "trade_id", "executed_at"),
    )
