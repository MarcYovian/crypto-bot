"""Order ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, Boolean, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.trades import Trade
    from src.database.models.executions import Execution


class Order(Base):
    """An order submitted to an exchange for a trade.

    Attributes:
        id: Auto-increment primary key.
        trade_id: FK to the parent trade.
        exchange_order_id: Exchange-side order ID (unique).
        client_order_id: Client-generated order ID.
        purpose: Order role (ENTRY, TP1, SL, etc.).
        order_type: Order type (MARKET, LIMIT, STOP_MARKET, etc.).
        side: ``BUY`` or ``SELL``.
        reduce_only: Flag indicating if order can only reduce position size.
        close_position: Flag indicating if order closes the whole position.
        time_in_force: Time in force policy (GTC, IOC, FOK, GTX).
        price: Order price (``None`` for market orders).
        qty: Order quantity.
        filled_qty: Cumulatively filled quantity.
        status: Order status (NEW, FILLED, CANCELED, etc.).
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    exchange_order_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    client_order_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)

    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)

    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="FALSE")
    close_position: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="FALSE")
    time_in_force: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="NEW")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    trade: Mapped["Trade"] = relationship(back_populates="orders")
    executions: Mapped[List["Execution"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("purpose IN ('ENTRY','TP1','TP2','TP3','SL','BEP_SL','TRAILING_SL','MANUAL_CLOSE')", name="chk_order_purpose"),
        CheckConstraint("order_type IN ('MARKET','LIMIT','STOP_MARKET','TAKE_PROFIT_MARKET','TRAILING_STOP_MARKET')", name="chk_order_type"),
        CheckConstraint("side IN ('BUY','SELL')", name="chk_order_side"),
        CheckConstraint("status IN ('NEW','PARTIALLY_FILLED','FILLED','CANCELED','EXPIRED','REJECTED')", name="chk_order_status"),
        Index("idx_orders_trade", "trade_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_exchange_order_id", "exchange_order_id"),
        Index("idx_orders_purpose", "purpose"),
        Index("idx_orders_trade_status", "trade_id", "status"),
        Index("idx_orders_purpose_status", "purpose", "status"),
    )
