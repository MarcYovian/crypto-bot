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


# =====================================================================
# 3. LIVE RISK SIMULATOR SANDBOX SCHEMAS
# =====================================================================

class RiskSimulationRequest(BaseSchema):
    """Request payload for live risk and position sizing simulation."""
    symbol: str = Field(..., min_length=2, max_length=30, description="Trading pair symbol (e.g. BTCUSDT)")
    side: str = Field(..., description="Trade direction: BUY or SELL")
    entry_price: float = Field(..., gt=0, description="Entry execution price")
    sl_price: float = Field(..., gt=0, description="Stop Loss price")
    wallet_balance: float = Field(..., gt=0, description="Account USDT balance")
    requested_leverage: int = Field(default=20, ge=1, le=125, description="Requested leverage multiplier")
    risk_percent: float = Field(default=2.0, gt=0, le=100, description="Risk percentage of balance")

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("BUY", "SELL"):
            raise ValueError("Side must be either 'BUY' or 'SELL'")
        return clean

    @field_validator("symbol")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        return v.strip().upper().replace("/", "").replace(":USDT", "")


class RiskSimulationResponse(BaseSchema):
    """Response payload with calculated position size, margin, downscaled leverage, and liquidation price."""
    symbol: str = Field(..., description="Trading pair symbol")
    side: str = Field(..., description="Trade direction")
    max_allowed_loss_usdt: float = Field(..., description="Strict maximum allowed loss in USDT")
    calculated_position_size: float = Field(..., description="Calculated contract / coin lot quantity")
    required_margin_usdt: float = Field(..., description="Required margin in USDT")
    effective_leverage: int = Field(..., description="Effective leverage after safety and bracket checks")
    is_leverage_downscaled: bool = Field(default=False, description="Flag indicating if leverage was downscaled")
    estimated_liquidation_price: float = Field(..., description="Estimated liquidation price in Isolated margin")
    stop_distance_usdt: float = Field(..., description="Absolute distance between entry and SL")
    projected_loss_at_sl_usdt: float = Field(..., description="Projected loss in USDT at Stop Loss level")
    is_safe: bool = Field(default=True, description="Safety check confirming SL is hit before liquidation and margin is affordable")

