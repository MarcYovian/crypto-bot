"""Pydantic schemas for Trades and Nested Trade Detail responses."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import Field, field_validator
from src.presentation.api.schemas.common import BaseSchema, TimestampMixin
from src.presentation.api.schemas.risk import TradeRiskRead
from src.presentation.api.schemas.order import OrderRead, ExecutionRead
from src.presentation.api.schemas.event_summary import TradeEventRead, TradeSummaryRead


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


# =====================================================================
# DASHBOARD API DTOs (OpenAPI 3.1.0 Specifications)
# =====================================================================

class ActiveTradeTPLevelDTO(BaseSchema):
    """Take-profit target milestone for live active position card."""
    level: int = Field(..., ge=1, le=3, description="TP index: 1, 2, or 3")
    price: float = Field(..., gt=0, description="Take profit target price")
    is_hit: bool = Field(default=False, description="Whether this TP level has been reached")


class ActiveTradeDTO(BaseSchema):
    """Real-time active open position representation for dashboard."""
    trade_id: int = Field(..., description="Trade primary key ID")
    symbol: str = Field(..., description="Trading pair ticker, e.g. BTCUSDT")
    side: str = Field(..., pattern="^(BUY|SELL)$", description="Order direction: BUY (LONG) or SELL (SHORT)")
    status: str = Field(..., description="Lifecycle status: WAITING_ENTRY, OPEN, PARTIAL")
    entry_price: Optional[float] = Field(default=None, description="Actual entry fill price")
    current_price: Optional[float] = Field(default=None, description="Latest live market price from Binance")
    sl_price: Optional[float] = Field(default=None, description="Stop loss price")
    position_size: float = Field(..., description="Original full position quantity")
    remaining_qty: float = Field(..., description="Unfilled / remaining open quantity")
    unrealized_pnl: float = Field(default=0.0, description="Live unrealized profit/loss in USDT")
    unrealized_pnl_percent: float = Field(default=0.0, description="Live unrealized ROI % based on position margin")
    leverage: int = Field(default=20, description="Position leverage")
    margin_mode: str = Field(default="ISOLATED", description="Margin mode: ISOLATED or CROSSED")
    tp_levels: List[ActiveTradeTPLevelDTO] = Field(default_factory=list, description="Target TP levels and hit status")
    opened_at: Optional[datetime] = Field(default=None, description="Timestamp when position was filled/opened")


class TradeHistoryItemDTO(BaseSchema):
    """Item summary in paginated historical trade log."""
    id: int = Field(..., description="Trade ID")
    symbol: str = Field(..., description="Trading pair ticker")
    side: str = Field(..., description="BUY or SELL")
    entry_price: Optional[float] = Field(default=None, description="Entry price")
    exit_price: Optional[float] = Field(default=None, description="Exit price")
    position_size: float = Field(..., description="Order quantity")
    net_pnl: Optional[float] = Field(default=None, description="Net PnL after commission/funding fees")
    roi_percent: Optional[float] = Field(default=None, description="Realized return on margin percentage")
    result: str = Field(..., description="Outcome: WIN, LOSS, BREAKEVEN, CANCELLED")
    close_reason: Optional[str] = Field(default=None, description="Trigger reason: TP1, TP2, TP3, SL, MANUAL_CLOSE")
    opened_at: Optional[datetime] = Field(default=None, description="Open timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="Close timestamp")


class PaginatedTradeHistoryDTO(BaseSchema):
    """Paginated trade history container."""
    total: int = Field(..., ge=0, description="Total matching historical trades")
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Number of items per page")
    items: List[TradeHistoryItemDTO] = Field(default_factory=list, description="List of closed trades")


class TradeRiskDetailDTO(BaseSchema):
    """Risk calculation metadata for a specific trade."""
    risk_amount_usdt: float = Field(..., description="Max risk allocated for this trade in USDT")
    stop_distance: float = Field(..., description="Absolute distance from entry to stop-loss")
    required_margin: float = Field(..., description="Initial margin committed in USDT")


class TradeOrderDetailDTO(BaseSchema):
    """Exchange order record detail."""
    id: int = Field(..., description="Internal order ID")
    exchange_order_id: Optional[str] = Field(default=None, description="Exchange order ID from Binance")
    purpose: str = Field(..., description="Order purpose: ENTRY, TP1, TP2, TP3, SL, MANUAL_CLOSE")
    order_type: str = Field(..., description="MARKET, LIMIT, STOP_MARKET")
    side: str = Field(..., description="BUY or SELL")
    price: Optional[float] = Field(default=None, description="Order price if limit")
    qty: float = Field(..., description="Order quantity")
    status: str = Field(..., description="Order status: NEW, FILLED, CANCELED, EXPIRED")


class TradeExecutionDetailDTO(BaseSchema):
    """Execution fill record."""
    price: float = Field(..., description="Execution fill price")
    qty: float = Field(..., description="Executed quantity")
    commission: float = Field(default=0.0, description="Fee in USDT")
    realized_pnl: float = Field(default=0.0, description="Realized PnL from this execution")
    executed_at: Optional[datetime] = Field(default=None, description="Execution timestamp")


class TradeEventDetailDTO(BaseSchema):
    """Trade lifecycle event log."""
    event_type: str = Field(..., description="Event name, e.g. TP1_HIT, SL_MOVED_TO_BEP")
    payload: Optional[str] = Field(default=None, description="Event payload JSON")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp")


class TradeSummaryDetailDTO(BaseSchema):
    """Performance summary of closed position."""
    gross_pnl: float = Field(..., description="Gross PnL")
    net_pnl: float = Field(..., description="Net PnL after commissions")
    commission: float = Field(..., description="Total commissions")
    roi: float = Field(..., description="ROI percentage")
    result: str = Field(..., description="WIN, LOSS, BREAKEVEN")


class TradeDetailDTO(BaseSchema):
    """Comprehensive trade detail with full 5-level nested relational tree."""
    trade_id: int = Field(..., description="Trade ID")
    symbol: str = Field(..., description="Trading pair ticker")
    side: str = Field(..., description="BUY or SELL")
    status: str = Field(..., description="Current status")
    entry_price: Optional[float] = Field(default=None, description="Entry price")
    sl_price: Optional[float] = Field(default=None, description="Stop loss price")
    position_size: float = Field(..., description="Total order quantity")
    leverage: int = Field(default=20, description="Leverage")
    risk_details: Optional[TradeRiskDetailDTO] = Field(default=None, description="Risk calculation metrics")
    orders: List[TradeOrderDetailDTO] = Field(default_factory=list, description="All associated orders")
    executions: List[TradeExecutionDetailDTO] = Field(default_factory=list, description="All fill executions")
    events: List[TradeEventDetailDTO] = Field(default_factory=list, description="Audit lifecycle events")
    summary: Optional[TradeSummaryDetailDTO] = Field(default=None, description="Closed trade performance summary")


class CloseTradeRequest(BaseSchema):
    """Payload to manually close an open position."""
    reason: str = Field(default="UI_MANUAL_CLOSE", description="Reason for closing the position")

