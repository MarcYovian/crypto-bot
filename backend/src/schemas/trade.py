"""Pydantic schemas for Trades and Nested Trade Detail responses."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import Field, field_validator
from src.schemas.common import BaseSchema, TimestampMixin
from src.schemas.risk import TradeRiskRead
from src.schemas.order import OrderRead, ExecutionRead
from src.schemas.event_summary import TradeEventRead, TradeSummaryRead


# =====================================================================
# TRADE SCHEMAS
# =====================================================================

class TradeBase(BaseSchema):
    """Base fields for Trade / Position."""
    account_id: int = Field(default=1, gt=0, description="FK to trading_accounts table")
    strategy_id: Optional[int] = Field(default=None, description="FK to strategies table")
    signal_id: Optional[int] = Field(default=None, description="FK to trading_signals table")
    instrument_id: int = Field(..., gt=0, description="FK to instruments table")
    side: str = Field(..., pattern="^(BUY|SELL)$", description="BUY or SELL")
    status: str = Field(default="WAITING_ENTRY", description="WAITING_ENTRY, OPEN, PARTIAL, CLOSED, CANCELLED")
    entry_price: Optional[Decimal] = Field(default=None, gt=0)
    avg_entry_price: Optional[Decimal] = Field(default=None, gt=0)
    sl_price: Decimal = Field(..., gt=0, description="Stop loss price")
    tp1_price: Optional[Decimal] = Field(default=None, gt=0)
    tp2_price: Optional[Decimal] = Field(default=None, gt=0)
    tp3_price: Optional[Decimal] = Field(default=None, gt=0)
    leverage: int = Field(default=20, ge=1, le=125, description="Position leverage")
    margin_mode: str = Field(default="ISOLATED", pattern="^(ISOLATED|CROSSED)$")
    position_size: Decimal = Field(..., gt=0, description="Total order quantity")
    remaining_qty: Decimal = Field(..., ge=0, description="Remaining open quantity")


class TradeCreate(TradeBase):
    """Payload for opening a new Trade."""
    pass


class TradeUpdate(BaseSchema):
    """Payload for updating general Trade fields."""
    entry_price: Optional[Decimal] = Field(default=None, gt=0)
    avg_entry_price: Optional[Decimal] = Field(default=None, gt=0)
    sl_price: Optional[Decimal] = Field(default=None, gt=0)
    tp1_price: Optional[Decimal] = Field(default=None, gt=0)
    tp2_price: Optional[Decimal] = Field(default=None, gt=0)
    tp3_price: Optional[Decimal] = Field(default=None, gt=0)
    remaining_qty: Optional[Decimal] = Field(default=None, ge=0)


class TradeStatusUpdate(BaseSchema):
    """Payload for lifecycle status updates."""
    status: str = Field(..., pattern="^(WAITING_ENTRY|OPEN|PARTIAL|CLOSED|CANCELLED)$")
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class TradeRead(TradeBase, TimestampMixin):
    """Basic response schema for a Trade."""
    id: int
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class TradeDetailRead(TradeRead):
    """Comprehensive Trade details with all nested child relationships."""
    trade_risk: Optional[TradeRiskRead] = None
    orders: List[OrderRead] = Field(default_factory=list)
    executions: List[ExecutionRead] = Field(default_factory=list)
    events: List[TradeEventRead] = Field(default_factory=list)
    summary: Optional[TradeSummaryRead] = None
