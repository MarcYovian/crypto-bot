"""Trade ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.trading_accounts import TradingAccount
    from src.database.models.strategies import Strategy
    from src.database.models.trading_signals import TradingSignal
    from src.database.models.instruments import Instrument
    from src.database.models.trade_risks import TradeRisk
    from src.database.models.orders import Order
    from src.database.models.executions import Execution
    from src.database.models.trade_events import TradeEvent
    from src.database.models.trade_summaries import TradeSummary


class Trade(Base):
    """A trade record representing a position.

    Tracks the position from ``WAITING_ENTRY`` through ``OPEN`` / ``PARTIAL``
    to ``CLOSED`` or ``CANCELLED``.

    Attributes:
        id: Auto-increment primary key.
        account_id: FK to trading_accounts table.
        strategy_id: FK to strategies table.
        signal_id: FK to originating trading_signals table.
        instrument_id: FK to instruments table.
        side: ``BUY`` or ``SELL``.
        status: Current lifecycle status.
        entry_price: Actual entry price (may be ``None`` until fill).
        avg_entry_price: Average fill price if multiple partial fills.
        sl_price: Stop-loss price.
        tp1_price / tp2_price / tp3_price: Take-profit prices.
        leverage: Position leverage.
        margin_mode: ``ISOLATED`` or ``CROSSED``.
        position_size: Order quantity.
        remaining_qty: Unfilled quantity.
        opened_at / closed_at: Timestamps for position lifecycle.
        created_at: Record creation timestamp.
        updated_at: Record update timestamp.
    """

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_accounts.id", ondelete="RESTRICT"), nullable=False)
    strategy_id: Mapped[Optional[int]] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trading_signals.id", ondelete="SET NULL"), nullable=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False)

    side: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="WAITING_ENTRY")

    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    avg_entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    sl_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    tp1_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    tp2_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)
    tp3_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 8), nullable=True)

    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="ISOLATED")
    position_size: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)

    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    account: Mapped["TradingAccount"] = relationship("TradingAccount")
    strategy: Mapped[Optional["Strategy"]] = relationship("Strategy")
    signal: Mapped[Optional["TradingSignal"]] = relationship(back_populates="trades")
    instrument: Mapped["Instrument"] = relationship("Instrument")

    trade_risk: Mapped[Optional["TradeRisk"]] = relationship(back_populates="trade", uselist=False, cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    executions: Mapped[List["Execution"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    events: Mapped[List["TradeEvent"]] = relationship(back_populates="trade", cascade="all, delete-orphan")
    summary: Mapped[Optional["TradeSummary"]] = relationship(back_populates="trade", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="chk_trade_side"),
        CheckConstraint("status IN ('WAITING_ENTRY','OPEN','PARTIAL','CLOSED','CANCELLED')", name="chk_trade_status"),
        CheckConstraint("margin_mode IN ('ISOLATED','CROSSED')", name="chk_trade_margin"),
        Index("idx_trade_account_id", "account_id"),
        Index("idx_trade_strategy_id", "strategy_id"),
        Index("idx_trade_signal_id", "signal_id"),
        Index("idx_trade_instrument_id", "instrument_id"),
        Index("idx_trade_status", "status"),
    )
