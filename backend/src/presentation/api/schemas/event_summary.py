"""Pydantic schemas for Trade Events and Trade Summaries."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import Field
from src.presentation.api.schemas.common import BaseSchema


# =====================================================================
# 1. TRADE EVENT SCHEMAS
# =====================================================================

class TradeEventBase(BaseSchema):
    """Base fields for Trade lifecycle audit event."""
    trade_id: int = Field(..., gt=0, description="FK to trades table")
    event_type: str = Field(..., description="Event identifier, e.g. SL_MOVED_TO_BEP, TP1_HIT, TRAILING_SL_UPDATED")
    payload_json: Optional[str] = Field(default=None, description="Optional raw JSON details")


class TradeEventCreate(TradeEventBase):
    """Payload for logging a trade event."""
    pass


class TradeEventRead(TradeEventBase):
    """Response schema for a Trade Event."""
    id: int
    created_at: Optional[datetime] = None


# =====================================================================
# 2. TRADE SUMMARY & PERFORMANCE SCHEMAS
# =====================================================================

class TradeSummaryBase(BaseSchema):
    """Base fields for closed Trade performance metrics."""
    trade_id: int = Field(..., gt=0, description="FK and PK to trades table")
    gross_pnl: Decimal = Field(..., description="Gross PnL before fees")
    net_pnl: Decimal = Field(..., description="Net PnL after commission and funding")
    commission: Decimal = Field(..., ge=0, description="Total commission fees")
    funding: Decimal = Field(default=Decimal("0"), description="Total funding fees")
    roi: Decimal = Field(..., description="Return on Margin (%)")
    rr: Decimal = Field(..., description="Risk-Reward ratio achieved")
    result: str = Field(..., pattern="^(WIN|LOSS|BREAKEVEN)$", description="Trade outcome: WIN, LOSS, BREAKEVEN")
    duration_seconds: int = Field(..., ge=0, description="Holding duration in seconds")
    close_reason: str = Field(..., description="Close trigger: TP1, TP2, TP3, SL, MANUAL_CLOSE, FORCE_CLOSE")
    closed_at: datetime = Field(..., description="Close timestamp")


class TradeSummaryCreate(TradeSummaryBase):
    """Payload for persisting Trade Summary."""
    pass


class TradeSummaryRead(TradeSummaryBase):
    """Response schema for Trade Summary."""
    pass


class PerformanceSummaryDTO(BaseSchema):
    """Aggregated trading statistics DTO."""
    total_trades: int = Field(default=0, ge=0)
    winning_trades: int = Field(default=0, ge=0)
    losing_trades: int = Field(default=0, ge=0)
    winrate: Decimal = Field(default=Decimal("0.0"), description="Winrate percentage (0.0 - 100.0%)")
    total_gross_pnl: Decimal = Field(default=Decimal("0.0"))
    total_net_pnl: Decimal = Field(default=Decimal("0.0"))
    total_commission: Decimal = Field(default=Decimal("0.0"))
    total_funding: Decimal = Field(default=Decimal("0.0"))
