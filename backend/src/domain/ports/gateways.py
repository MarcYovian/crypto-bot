"""Abstract gateway ports for interacting with external services (Exchanges, Telegram, etc.)."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from src.domain.value_objects.side import OrderSide, MarginMode
from src.domain.value_objects.trade_status import OrderType
from src.domain.value_objects.leverage import Leverage
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity


class IExchangeGateway(ABC):
    """Abstract Port for cryptocurrency exchange interaction (Binance, CCXT, etc.)."""

    @abstractmethod
    async def get_balance(self) -> Dict[str, Any]:
        """Fetch total and free account wallet balances."""
        ...

    @abstractmethod
    async def fetch_balance(self) -> Dict[str, Any]:
        """Alias for get_balance."""
        ...

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price and book quotes."""
        ...

    @abstractmethod
    async def fetch_ticker_price(self, symbol: str) -> Decimal:
        """Fetch current realtime mark/last price for a symbol as Decimal."""
        ...

    @abstractmethod
    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: Optional[int] = None,
        limit: int = 30,
    ) -> List[List[Any]]:
        """Fetch OHLCV candlestick data for a symbol."""
        ...

    @abstractmethod
    async def has_price_reached_target(
        self,
        symbol: str,
        target_price: Decimal,
        side: str,
        since_timestamp_ms: Optional[int] = None,
        limit: int = 30,
    ) -> bool:
        """Check whether historical candles touched or exceeded a target price (e.g. TP1 / SL)."""
        ...

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: Union[int, Leverage]) -> Dict[str, Any]:
        """Set position leverage on exchange."""
        ...

    @abstractmethod
    async def set_margin_mode(self, symbol: str, margin_mode: Union[MarginMode, str]) -> Dict[str, Any]:
        """Set ISOLATED or CROSSED margin mode."""
        ...

    @abstractmethod
    async def set_position_mode(self, dual_side_position: bool = False) -> Dict[str, Any]:
        """Set One-Way Position mode (dual_side_position=False) or Hedge Mode."""
        ...

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: Union[OrderSide, str],
        order_type: Union[OrderType, str],
        qty: Union[Decimal, Quantity, float],
        price: Optional[Union[Decimal, Price, float]] = None,
        stop_price: Optional[Union[Decimal, Price, float]] = None,
        client_order_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a single order (MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET)."""
        ...

    @abstractmethod
    async def create_entry_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """Submit an Entry order (MARKET or LIMIT)."""
        ...

    @abstractmethod
    async def create_stop_loss_order(
        self,
        symbol: str,
        side: str,
        stop_price: Decimal,
        qty: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        close_position: bool = True,
        working_type: str = "MARK_PRICE",
    ) -> Dict[str, Any]:
        """Submit a Stop Loss order (STOP_MARKET)."""
        ...

    @abstractmethod
    async def create_take_profit_order(
        self,
        symbol: str,
        side: str,
        tp_price: Decimal,
        qty: Decimal,
        client_order_id: Optional[str] = None,
        working_type: str = "MARK_PRICE",
    ) -> Dict[str, Any]:
        """Submit a Take Profit Market order."""
        ...

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        exchange_order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an open order by exchange order ID or client order ID."""
        ...

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Cancel all open orders for a symbol."""
        ...

    @abstractmethod
    async def cancel_all_open_orders(self, symbol: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Alias for cancel_all_orders."""
        ...

    @abstractmethod
    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch active open orders."""
        ...

    @abstractmethod
    async def fetch_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the current status and execution details of a specific order."""
        ...

    @abstractmethod
    async def fetch_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open futures positions."""
        ...

    @abstractmethod
    async def fetch_leverage_brackets(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch leverage bracket tiers."""
        ...

    @abstractmethod
    async def fetch_instruments_metadata(self) -> List[Dict[str, Any]]:
        """Fetch active trading pairs and precision rules from exchange."""
        ...

    @abstractmethod
    def reconfigure(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """Dynamically update client API credentials and network mode."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close exchange client connections."""
        ...

    async def watch_orders_stream(self, callback_coro: Any) -> None:
        """Subscribe and stream live order fill status updates. Default no-op for gateways without streaming."""
        pass

    def start_order_stream_task(self, on_fill_coro: Any) -> Optional[Any]:
        """Start background order stream task if supported."""
        return None


class INotificationGateway(ABC):
    """Abstract Port for outgoing user notifications and interactive UI (Telegram, Webhook, etc.)."""

    @abstractmethod
    async def send_message(
        self,
        text: str,
        chat_id: Optional[Union[int, str]] = None,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Any] = None,
    ) -> Any:
        """Send formatted text notification."""
        ...

    @abstractmethod
    async def send_alert(
        self,
        title: str,
        message: str,
        level: str = "INFO",
        chat_id: Optional[Union[int, str]] = None,
    ) -> Any:
        """Send urgent system or risk alert."""
        ...

    @abstractmethod
    async def send_signal_confirmation(
        self,
        chat_id: Optional[Union[str, int]] = None,
        signal_id: Optional[int] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        entry_range: Optional[str] = None,
        sl: Optional[Decimal] = None,
        tp_targets: Optional[List[Decimal]] = None,
        confidence: Optional[Decimal] = None,
        text: Optional[str] = None,
        reply_markup: Optional[Any] = None,
    ) -> Any:
        """Send new trading signal alert with interactive Approve / Reject Inline buttons."""
        ...

    @abstractmethod
    async def send_trade_opened_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        entry_price: Any = None,
        leverage: int = 1,
        position_size: Any = None,
        margin: Any = None,
        sl_price: Any = None,
        tp_targets: Optional[List[Any]] = None,
        notional_value: Optional[Any] = None,
        risk_amount: Optional[Any] = None,
        risk_percent: Optional[Any] = None,
        tp_allocations: Optional[List[Any]] = None,
        risk_reward_ratios: Optional[List[Any]] = None,
        requested_leverage: Optional[int] = None,
        is_leverage_downscaled: bool = False,
        leverage_reason: Optional[str] = None,
        order_type: str = "MARKET",
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Any:
        """Send comprehensive trade open confirmation alert."""
        ...

    @abstractmethod
    async def send_take_profit_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        tp_level: int = 1,
        exit_price: Any = None,
        closed_qty: Any = None,
        realized_pnl: Any = None,
        remaining_qty: Any = None,
        price_precision: Optional[int] = None,
        qty_precision: Optional[int] = None,
    ) -> Any:
        """Send take profit fill notification."""
        ...

    @abstractmethod
    async def send_stop_loss_moved_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        new_sl_price: Any = None,
        reason: str = "TP1 reached (Moved to Break-Even)",
        old_sl_price: Optional[Any] = None,
        price_precision: Optional[int] = None,
    ) -> Any:
        """Send notification when SL is shifted to BEP or Trailing Stop."""
        ...

    @abstractmethod
    async def send_trade_closed_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        side: str = "",
        exit_price: Any = None,
        total_pnl: Any = None,
        total_pnl_percent: Optional[Any] = None,
        result: str = "WIN",
        close_reason: str = "TP3 Hit",
        duration_minutes: Optional[int] = None,
        price_precision: Optional[int] = None,
    ) -> Any:
        """Send position close summary notification."""
        ...

    @abstractmethod
    async def send_panic_close_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        closed_count: int = 0,
        total_realized_pnl: Optional[Decimal] = None,
        symbols_closed: Optional[List[str]] = None,
    ) -> Any:
        """Send emergency panic close all broadcast alert."""
        ...

    @abstractmethod
    async def send_circuit_breaker_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        daily_loss_usdt: Any = None,
        daily_loss_percent: Any = None,
        max_daily_loss_percent: Any = None,
        total_balance: Any = None,
    ) -> Any:
        """Send daily risk limit / circuit breaker trigger alert."""
        ...

    @abstractmethod
    async def send_signal_rejected_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        reason: str = "",
        raw_signal: Optional[str] = None,
    ) -> Any:
        """Send notification when a signal is rejected."""
        ...

    @abstractmethod
    async def send_price_runaway_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        symbol: str = "",
        signal_entry: Any = None,
        current_price: Any = None,
        deviation_percent: Any = None,
        reason: str = "Price moved > 2.0% away from entry",
    ) -> Any:
        """Send alert when price deviates too far from signal entry."""
        ...

    @abstractmethod
    async def send_daily_summary_alert(
        self,
        chat_id: Optional[Union[str, int]] = None,
        date_str: str = "",
        total_trades: int = 0,
        win_count: int = 0,
        loss_count: int = 0,
        win_rate: float = 0.0,
        net_pnl_usdt: Decimal = Decimal("0"),
        profit_factor: float = 0.0,
    ) -> Any:
        """Send end-of-day performance scorecard."""
        ...

    @abstractmethod
    async def edit_message_text(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Any] = None,
    ) -> Any:
        """Edit an existing sent message (for interactive wizard/cards)."""
        ...

    @abstractmethod
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Any:
        """Acknowledge an inline button click."""
        ...

    @abstractmethod
    async def set_my_commands(
        self,
        commands: Optional[List[Dict[str, str]]] = None,
    ) -> Any:
        """Register the bot command menu with Telegram UI."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close notification gateway connection/session."""
        ...
