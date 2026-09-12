"""TradeEvent ORM model."""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Text, Integer, DateTime, ForeignKey, CheckConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.trades import Trade


class TradeEvent(Base):
    """A lifecycle event logged for a trade.

    Attributes:
        id: Auto-increment primary key.
        trade_id: FK to the parent trade.
        event_type: Event category (ENTRY, TP1, SL, etc.).
        payload_json: Optional JSON payload with event details.
        created_at: Event timestamp.
    """

    __tablename__ = "trade_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    trade: Mapped["Trade"] = relationship(back_populates="events")

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ENTRY','ENTRY_FILLED','TP1','TP2','TP3','SL','SL_UPDATE','SL_MOVED_TO_BEP','SL_MOVED_TO_TP1','TRAILING_ENABLED','MANUAL_CLOSE','FORCE_CLOSE','FAILSAFE_SYNC','FUNDING','TP1_HIT','TP2_HIT','TRAILING_SL_UPDATED','LIQUIDATION_WARNING','ORDER_ERROR')",
            name="chk_event_type"
        ),

        Index("idx_trade_events_trade", "trade_id"),
        Index("idx_trade_events_trade_time", "trade_id", "created_at"),
    )
