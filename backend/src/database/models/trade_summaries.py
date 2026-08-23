"""TradeSummary ORM model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.connection import Base

if TYPE_CHECKING:
    from src.database.models.trades import Trade


class TradeSummary(Base):
    """Performance summary computed when a trade is closed.

    Attributes:
        trade_id: FK to the trade (PK).
        gross_pnl: Gross profit / loss before fees.
        net_pnl: Profit / loss after commission and funding.
        commission: Total fees paid.
        funding: Total funding rate cost.
        roi: Return on margin (%).
        rr: Risk-reward ratio.
        result: Trade result state (WIN, LOSS, BREAKEVEN).
        duration_seconds: Trade duration in seconds.
        close_reason: Why the trade closed (TP3, SL, MANUAL_CLOSE, etc.).
        closed_at: Close timestamp.
    """

    __tablename__ = "trade_summary"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), primary_key=True)
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    funding: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    roi: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    rr: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    
    result: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    close_reason: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    trade: Mapped["Trade"] = relationship(back_populates="summary")

    __table_args__ = (
        CheckConstraint("result IN ('WIN','LOSS','BREAKEVEN')", name="chk_summary_result"),
        Index("idx_trade_summary_result", "result"),
    )
