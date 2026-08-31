"""Data Transfer Objects and Commands for Trade Use Cases."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import TradeStatus, OrderStatus, OrderPurpose, OrderType
from src.domain.entities.signal import ParsedSignalDTO


@dataclass(frozen=True)
class ExecuteSignalCommand:
    """Command payload to trigger end-to-end signal execution."""

    signal_dto: ParsedSignalDTO
    account_id: int = 1
    signal_id: Optional[int] = None
    strategy_id: Optional[int] = None
    auto_tp_sl: bool = True
    is_manual: bool = False



@dataclass(frozen=True)
class CloseTradeCommand:
    """Command payload to close a single trade manually or via emergency trigger."""

    trade_id: int
    reason: str = "MANUAL_CLOSE"  # "MANUAL_CLOSE", "PANIC_CLOSE", "LIQUIDATION_FAILSAFE"
    account_id: int = 1


@dataclass(frozen=True)
class UpdateStopLossCommand:
    """Command payload to dynamically adjust a trade's stop-loss price."""

    trade_id: int
    new_sl_price: Decimal
    reason: str = "BEP_AFTER_TP1"  # "BEP_AFTER_TP1", "TRAILING_AFTER_TP2", "MANUAL_ADJUST"


@dataclass(frozen=True)
class SyncPositionsCommand:
    """Command payload to trigger reconciliation between Binance exchange and database."""

    account_id: int = 1


@dataclass(frozen=True)
class OrderFillPayload:
    """Payload representing an exchange execution report (fill) from WebSocket / REST."""

    symbol: str
    exchange_order_id: str
    client_order_id: Optional[str]
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    fill_price: Decimal
    fill_qty: Decimal
    cumulative_filled_qty: Decimal
    fee: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    trade_id: Optional[int] = None
    order_id: Optional[int] = None
    purpose: Optional[OrderPurpose] = None
    realized_pnl: Optional[Decimal] = None


@dataclass
class TradeExecutionResultDTO:
    """Result data returned from executing a signal."""

    trade_id: Optional[int]
    symbol: str
    side: str
    status: str
    position_size: Decimal
    entry_price: Decimal
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_ids: List[str] = field(default_factory=list)
    is_success: bool = True
    message: str = "Success"

    @property
    def success(self) -> bool:
        return self.is_success

    @property
    def execution_type(self) -> str:
        return "LIMIT" if self.status == "WAITING_ENTRY" else "MARKET"


@dataclass(frozen=True)
class PlaceBracketOrdersCommand:
    """Command payload to place Stop-Loss and multi-Take-Profit bracket orders for an active trade."""

    trade_id: int
    symbol: str
    side: Union[OrderSide, str]
    position_size: Decimal
    sl_price: Optional[Decimal] = None
    tp_targets: Optional[List[Decimal]] = None
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    auto_tp_sl: bool = True
    is_emergency_close_on_sl_fail: bool = True


@dataclass
class BracketOrdersResultDTO:
    """Result returned after placing bracket SL and TP orders."""

    trade_id: int
    sl_order_id: Optional[str] = None
    tp_order_ids: List[str] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None


