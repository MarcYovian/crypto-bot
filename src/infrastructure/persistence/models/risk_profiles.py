"""RiskProfile ORM model."""

from decimal import Decimal
from typing import List, TYPE_CHECKING
from sqlalchemy import Text, Integer, Numeric, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.daily_risk_configs import DailyRiskConfig


class RiskProfile(Base):
    """Risk management settings profile.

    Attributes:
        id: Primary key (Auto increment).
        name: Profile name identifier (e.g. LOW_RISK, AGGRESSIVE).
        risk_percent: Percentage of balance per trade (e.g. 1.5%).
        max_daily_loss: Maximum allowable daily loss percentage or amount.
        max_open_trade: Maximum parallel open positions allowed.
        is_active: Active status flag.
    """

    __tablename__ = "risk_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    risk_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    max_open_trade: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")

    # Relationships
    daily_risk_configs: Mapped[List["DailyRiskConfig"]] = relationship(
        "DailyRiskConfig", back_populates="risk_profile", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_risk_profiles_is_active", "is_active"),
    )
