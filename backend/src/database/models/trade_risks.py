"""TradeRisk ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Integer, Numeric, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.trades import Trade
    from src.database.models.daily_risk_configs import DailyRiskConfig


class TradeRisk(Base):
    """Risk-calculation detail linked to a trade.

    Attributes:
        trade_id: FK to the trade (PK).
        daily_risk_id: FK to daily_risk_config table.
        entry: Entry price.
        stop: Stop-loss price.
        stop_distance: Absolute stop distance.
        qty: Calculated position quantity.
        margin: Required margin in USDT.
        risk_amount: Calculated risk amount in USDT.
        leverage: Leverage used.
        created_at: Record creation timestamp.
    """

    __tablename__ = "trade_risk"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True)
    daily_risk_id: Mapped[int] = mapped_column(ForeignKey("daily_risk_config.id", ondelete="RESTRICT"), nullable=False)

    entry: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    stop: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    stop_distance: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    margin: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # Relationships
    trade: Mapped["Trade"] = relationship(back_populates="trade_risk")
    daily_risk: Mapped["DailyRiskConfig"] = relationship(back_populates="trade_risks")

    __table_args__ = (
        Index("idx_trade_risk_daily_risk_id", "daily_risk_id"),
    )
