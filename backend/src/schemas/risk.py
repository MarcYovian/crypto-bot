"""Pydantic schemas for Daily Risk and Trade Risk calculations."""

from datetime import date as py_date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import Field, field_validator
from src.schemas.common import BaseSchema


# =====================================================================
# 1. DAILY RISK CONFIG SCHEMAS
# =====================================================================

class DailyRiskConfigBase(BaseSchema):
    """Base fields for Daily Risk Snapshot."""
    account_id: int = Field(..., gt=0, description="FK to trading_accounts table")
    risk_profile_id: int = Field(..., gt=0, description="FK to risk_profiles table")
    date: py_date = Field(..., description="Snapshot date (YYYY-MM-DD)")
    balance: Decimal = Field(..., gt=0, description="Locked total equity at 00:00 WIB")
    risk_amount: Decimal = Field(..., gt=0, description="Maximum risk budget for the day")


class DailyRiskConfigCreate(DailyRiskConfigBase):
    """Payload for saving Daily Risk Snapshot."""
    pass


class DailyRiskConfigRead(DailyRiskConfigBase):
    """Response schema for Daily Risk Snapshot."""
    id: int
    created_at: Optional[datetime] = None


# =====================================================================
# 2. TRADE RISK SCHEMAS & CALCULATION DTO
# =====================================================================

class RiskCalculationResultDTO(BaseSchema):
    """Data Transfer Object returned by the Risk Calculator engine."""
    entry_price: Decimal = Field(..., gt=0)
    stop_loss_price: Decimal = Field(..., gt=0)
    stop_distance: Decimal = Field(..., gt=0, description="Absolute distance between entry and SL")
    risk_amount: Decimal = Field(..., gt=0, description="USDT amount at risk (e.g. 2.0% of balance)")
    position_size: Decimal = Field(..., gt=0, description="Calculated contract / coin quantity")
    required_margin: Decimal = Field(..., gt=0, description="Margin needed for position")
    leverage: int = Field(default=20, ge=1, le=125)


class TradeRiskBase(BaseSchema):
    """Base fields for per-trade risk breakdown."""
    trade_id: int = Field(..., gt=0, description="FK and PK to trades table")
    daily_risk_id: int = Field(..., gt=0, description="FK to daily_risk_config table")
    entry: Decimal = Field(..., gt=0)
    stop: Decimal = Field(..., gt=0)
    stop_distance: Decimal = Field(..., gt=0)
    qty: Decimal = Field(..., gt=0)
    margin: Decimal = Field(..., gt=0)
    risk_amount: Decimal = Field(..., gt=0)
    leverage: int = Field(default=20, ge=1, le=125)


class TradeRiskCreate(TradeRiskBase):
    """Payload for saving Trade Risk record."""
    pass


class TradeRiskRead(TradeRiskBase):
    """Response schema for Trade Risk."""
    created_at: Optional[datetime] = None
