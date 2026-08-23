"""Domain DTO entities for trade execution and order fill reports."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


@dataclass
class OrderFillDTO:
    """Standardized DTO for exchange order fill execution events."""
    order_id: int
    trade_id: int
    symbol: str
    side: str  # "BUY" or "SELL"
    purpose: str  # "ENTRY", "STOP_LOSS", "TAKE_PROFIT_1", "TAKE_PROFIT_2", "TAKE_PROFIT_3"
    fill_price: Decimal
    fill_qty: Decimal
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    fee: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    status: str = "FILLED"
    realized_pnl: Decimal = Decimal("0")
    timestamp: Optional[datetime] = None


@dataclass
class TradeExecutionResultDTO:
    """Result DTO for trade initiation orchestration."""
    symbol: str
    side: str
    status: str
    trade_id: Optional[int] = None
    position_size: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_ids: List[str] = field(default_factory=list)
    is_success: bool = True
    message: str = ""
