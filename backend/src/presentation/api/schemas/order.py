"""Pydantic schemas for Orders and Executions."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import Field, field_validator
from src.presentation.api.schemas.common import BaseSchema, TimestampMixin


# =====================================================================
# 1. ORDER SCHEMAS
# =====================================================================

class OrderBase(BaseSchema):
    """Base fields for an Order submitted to the exchange."""
    trade_id: int = Field(..., gt=0, description="FK to trades table")
    exchange_order_id: Optional[str] = Field(default=None, description="Exchange-assigned order ID")
    client_order_id: Optional[str] = Field(default=None, description="Client-generated unique order ID")
    purpose: str = Field(..., description="ENTRY, TP1, TP2, TP3, SL, BEP_SL, TRAILING_SL, MANUAL_CLOSE")
    order_type: str = Field(..., description="MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET")
    side: str = Field(..., pattern="^(BUY|SELL)$", description="BUY or SELL")
    reduce_only: bool = Field(default=False)
    close_position: bool = Field(default=False)
    time_in_force: Optional[str] = Field(default="GTC", description="GTC, IOC, FOK, GTX")
    price: Optional[Decimal] = Field(default=None, gt=0, description="Limit price (None for market orders)")
    qty: Decimal = Field(..., gt=0, description="Order quantity")
    filled_qty: Decimal = Field(default=Decimal("0"), ge=0, description="Cumulatively filled quantity")
    status: str = Field(default="NEW", description="NEW, PARTIALLY_FILLED, FILLED, CANCELED, EXPIRED, REJECTED")


class OrderCreate(OrderBase):
    """Payload for persisting an Order."""
    pass


class OrderUpdate(BaseSchema):
    """Payload for updating an Order."""
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    filled_qty: Optional[Decimal] = None
    status: Optional[str] = None
    price: Optional[Decimal] = None


class OrderStatusUpdate(BaseSchema):
    """Payload for updating order status from WebSocket fill events."""
    exchange_order_id: str
    status: str
    filled_qty: Optional[Decimal] = Field(default=None, ge=0)


class OrderRead(OrderBase, TimestampMixin):
    """Response schema for an Order."""
    id: int


# =====================================================================
# 2. EXECUTION SCHEMAS
# =====================================================================

class ExecutionBase(BaseSchema):
    """Base fields for an execution / partial fill."""
    order_id: Optional[int] = Field(default=None, description="FK to orders table")
    trade_id: int = Field(..., gt=0, description="FK to trades table")
    price: Decimal = Field(..., gt=0, description="Fill price")
    qty: Decimal = Field(..., gt=0, description="Filled quantity")
    commission: Decimal = Field(default=Decimal("0"), ge=0, description="Commission fee")
    commission_asset: str = Field(default="USDT", description="Fee asset, e.g. USDT, BNB")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized PnL for this execution")
    is_maker: bool = Field(default=False, description="Whether fill was maker order")


class ExecutionCreate(ExecutionBase):
    """Payload for recording a new fill execution."""
    pass


class ExecutionRead(ExecutionBase):
    """Response schema for Execution."""
    id: int
    executed_at: Optional[datetime] = None
