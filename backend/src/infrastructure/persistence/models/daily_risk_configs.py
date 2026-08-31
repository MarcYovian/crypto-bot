"""DailyRiskConfig ORM model."""

from datetime import datetime, date
from decimal import Decimal
from typing import List, TYPE_CHECKING
from sqlalchemy import Integer, Date, Numeric, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.persistence.connection import Base

if TYPE_CHECKING:
    from src.infrastructure.persistence.models.trading_accounts import TradingAccount
    from src.infrastructure.persistence.models.risk_profiles import RiskProfile
    from src.infrastructure.persistence.models.trade_risks import TradeRisk


class DailyRiskConfig(Base):
    """Daily risk snapshot: account balance and per-trade risk budget.

    Attributes:
        id: Auto-increment primary key.
        account_id: FK to trading_accounts table.
        risk_profile_id: FK to risk_profiles table.
        date: Snapshot date.
        balance: Total balance at snapshot time.
        risk_amount: Pre-calculated risk amount.
        created_at: Record creation timestamp.
    """

    __tablename__ = "daily_risk_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("trading_accounts.id", ondelete="RESTRICT"), nullable=False)
    risk_profile_id: Mapped[int] = mapped_column(ForeignKey("risk_profiles.id", ondelete="RESTRICT"), nullable=False)
    
    date: Mapped[date] = mapped_column(Date, nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    daily_risk_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # Relationships
    account: Mapped["TradingAccount"] = relationship("TradingAccount")
    risk_profile: Mapped["RiskProfile"] = relationship("RiskProfile", back_populates="daily_risk_configs")
    trade_risks: Mapped[List["TradeRisk"]] = relationship(back_populates="daily_risk")

    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uk_daily_risk_account_date"),
        Index("idx_daily_risk_date", "date"),
        Index("idx_daily_risk_account_id", "account_id"),
        Index("idx_daily_risk_profile_id", "risk_profile_id"),
    )
