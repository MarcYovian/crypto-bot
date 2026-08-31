"""Abstract repository port contracts for data persistence.

Defines the complete domain-level interface requirements for all repository adapters.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


class IBaseRepository(ABC):
    """Generic base repository port contract."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        """Fetch record by primary key."""
        ...

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Any]:
        """Fetch paginated records."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        """Create and persist a new record."""
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        """Update an existing record."""
        ...

    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete a record by primary key."""
        ...

    @abstractmethod
    async def save(self, entity: Any) -> Any:
        """Save or synchronize aggregate/entity state."""
        ...


class ITradeRepository(ABC):
    """Abstract Port for Trade Aggregate and lifecycle persistence."""

    @abstractmethod
    async def get(self, trade_id: int) -> Optional[Any]:
        """Fetch trade by primary key ID."""
        ...

    @abstractmethod
    async def get_detail(self, trade_id: int) -> Optional[Any]:
        """Fetch trade with relations (instrument, orders, events, summary) loaded."""
        ...

    @abstractmethod
    async def get_with_instrument(self, trade_id: int) -> Optional[Any]:
        """Fetch trade with its instrument loaded."""
        ...

    @abstractmethod
    async def get_active_trade_by_instrument(self, instrument_id: int) -> Optional[Any]:
        """Fetch active trade for a specific instrument ID."""
        ...

    @abstractmethod
    async def get_active_trade_by_symbol(self, symbol: str, account_id: Optional[int] = None) -> Optional[Any]:
        """Fetch active trade for a given symbol."""
        ...

    @abstractmethod
    async def count_active_trades(self, account_id: int) -> int:
        """Count active trades for an account."""
        ...

    async def count_open_positions(self, account_id: Optional[int] = None) -> int:
        """Count active open positions."""
        return await self.count_active_trades(account_id or 1)

    @abstractmethod
    async def get_all_active_trades(self, account_id: Optional[int] = None) -> List[Any]:
        """Fetch all trades with status in WAITING_ENTRY, OPEN, PARTIAL."""
        ...

    async def get_active_trades(self, account_id: Optional[int] = None) -> List[Any]:
        """Alias for get_all_active_trades."""
        return await self.get_all_active_trades(account_id)

    @abstractmethod
    async def get_active_trades_with_instrument(self, account_id: Optional[int] = None) -> List[Any]:
        """Fetch active trades with eagerly loaded instrument relation."""
        ...

    @abstractmethod
    async def get_expired_waiting_trades(self, max_hours: int = 4) -> List[Any]:
        """Fetch hanging WAITING_ENTRY trades older than max_hours."""
        ...

    @abstractmethod
    async def update_entry_fill(
        self,
        trade_id: int,
        entry_price: Decimal,
        avg_entry_price: Optional[Decimal] = None,
        opened_at: Optional[datetime] = None,
        filled_qty: Optional[Decimal] = None,
    ) -> Optional[Any]:
        """Transition trade from WAITING_ENTRY to OPEN upon fill."""
        ...

    @abstractmethod
    async def update_sl_price(self, trade_id: int, new_sl_price: Decimal) -> Optional[Any]:
        """Update stop loss price level."""
        ...

    async def update_stop_loss(self, trade_id: int, new_sl_price: Decimal) -> Optional[Any]:
        """Alias for update_sl_price."""
        return await self.update_sl_price(trade_id, new_sl_price)

    @abstractmethod
    async def reduce_position_qty(
        self, trade_id: int, closed_qty: Decimal, is_closed: bool = False
    ) -> Optional[Any]:
        """Reduce remaining quantity upon partial fill or close."""
        ...

    @abstractmethod
    async def update_partial_close(
        self,
        trade_id: int,
        closed_qty: Decimal,
        remaining_qty: Optional[Decimal] = None,
        realized_pnl: Optional[Decimal] = None,
    ) -> Optional[Any]:
        """Update trade on partial TP fill."""
        ...

    @abstractmethod
    async def update_trade_status(self, trade_id: int, schema: Any) -> Optional[Any]:
        """Update trade status and timestamps."""
        ...

    @abstractmethod
    async def get_closed_trades_history(
        self,
        account_id: int,
        skip: int = 0,
        limit: int = 50,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Any]:
        """Fetch historical closed and cancelled trades."""
        ...

    @abstractmethod
    async def get_active_positions_with_relations(self, account_id: int) -> List[Any]:
        """Fetch active trades with instrument, orders, and events."""
        ...

    @abstractmethod
    async def get_history_paginated(
        self,
        account_id: int,
        page: int = 1,
        page_size: int = 20,
        symbol: Optional[str] = None,
        result: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[int, List[Any]]:
        """Fetch paginated trade history with filters."""
        ...

    @abstractmethod
    async def get_closed_trades_for_report(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Any]:
        """Fetch all closed trades for summary reporting."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, trade: Any) -> Any:
        ...


class IOrderRepository(ABC):
    """Abstract Port for Order persistence and execution tracking."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_exchange_order_id(self, exchange_order_id: str) -> Optional[Any]:
        """Fetch order by exchange-assigned order ID."""
        ...

    @abstractmethod
    async def get_by_client_order_id(self, client_order_id: str) -> Optional[Any]:
        """Fetch order by bot client_order_id."""
        ...

    @abstractmethod
    async def get_orders_by_trade_id(self, trade_id: int) -> List[Any]:
        """Fetch all orders attached to a trade position."""
        ...

    async def get_open_orders_by_trade(self, trade_id: int) -> List[Any]:
        """Fetch active orders for a trade."""
        return await self.get_open_orders_by_trade_id(trade_id)

    @abstractmethod
    async def get_open_orders_by_trade_id(self, trade_id: int) -> List[Any]:
        """Fetch active orders ('NEW' or 'PARTIALLY_FILLED') on a trade."""
        ...

    @abstractmethod
    async def get_orders_by_purpose(self, trade_id: int, purpose: str) -> List[Any]:
        """Fetch orders with a specific purpose (ENTRY, TP1, TP2, TP3, SL)."""
        ...

    @abstractmethod
    async def cancel_all_open_orders_for_trade(self, trade_id: int) -> int:
        """Bulk update open orders to CANCELED for a trade."""
        ...

    @abstractmethod
    async def cancel_all_active_orders(self) -> int:
        """Bulk cancel all active orders across trades."""
        ...

    @abstractmethod
    async def update_order_fill(
        self, exchange_order_id: str, status: str, filled_qty: Optional[Decimal] = None
    ) -> Optional[Any]:
        """Update order fill status and cumulative quantity."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, order: Any) -> Any:
        ...


class IInstrumentRepository(ABC):
    """Abstract Port for Instrument and Pair metadata access."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_symbol(self, symbol: str, exchange_id: Optional[int] = None) -> Optional[Any]:
        """Fetch instrument metadata by trading pair symbol."""
        ...

    @abstractmethod
    async def get_all_active(self, exchange_id: Optional[int] = None) -> List[Any]:
        """Fetch all active instruments."""
        ...

    @abstractmethod
    async def get_all_instruments_with_brackets(self, exchange_id: Optional[int] = None) -> List[Any]:
        """Fetch all instruments with loaded leverage brackets."""
        ...

    async def get_whitelisted_symbols(self) -> List[str]:
        """Fetch symbols of all active instruments."""
        active = await self.get_all_active()
        return [getattr(x, "symbol", "") for x in active if getattr(x, "symbol", "")]

    @abstractmethod
    async def bulk_upsert_instruments(self, instruments: Sequence[Any]) -> int:
        """Insert or update synced instrument metadata."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, instrument: Any) -> Any:
        ...


class IInstrumentLeverageBracketRepository(ABC):
    """Abstract Port for Instrument leverage bracket tiers."""

    async def get_by_instrument_id(self, instrument_id: int) -> List[Any]:
        return await self.get_brackets_by_instrument(instrument_id)

    @abstractmethod
    async def get_brackets_by_instrument(self, instrument_id: int) -> List[Any]:
        """Fetch all leverage brackets for an instrument sorted by tier."""
        ...

    @abstractmethod
    async def get_bracket_for_notional(self, instrument_id: int, notional_value: Decimal) -> Optional[Any]:
        """Find matching leverage bracket for notional value."""
        ...

    @abstractmethod
    async def get_max_leverage_for_symbol(self, instrument_id: int) -> int:
        """Fetch absolute max leverage allowable for an instrument."""
        ...

    @abstractmethod
    async def bulk_upsert_brackets(self, instrument_id: int, brackets: List[Any]) -> int:
        """Bulk update leverage brackets."""
        ...

    async def sync_brackets(self, instrument_id: int, brackets_data: List[Dict[str, Any]]) -> None:
        await self.bulk_upsert_brackets(instrument_id, brackets_data)


class IWatchlistRepository(ABC):
    """Abstract Port for Whitelisted symbols and active trading pairs."""

    @abstractmethod
    async def get_by_instrument_id(self, instrument_id: int) -> Optional[Any]:
        ...

    async def is_symbol_whitelisted(self, symbol: str) -> bool:
        return await self.is_symbol_enabled(symbol)

    @abstractmethod
    async def is_symbol_enabled(self, symbol: str) -> bool:
        """Check if trading is enabled for a given symbol."""
        ...

    @abstractmethod
    async def get_enabled_watchlist_with_instruments(self) -> List[Any]:
        """Fetch enabled watchlist entries with instrument relation."""
        ...

    @abstractmethod
    async def get_all_active(self) -> List[Any]:
        """Fetch all active enabled watchlist entries with instrument relation."""
        ...

    @abstractmethod
    async def get_all_watchlist_with_instruments(self) -> List[Any]:
        """Fetch all watchlist entries."""
        ...

    @abstractmethod
    async def get_active_watchlist(self) -> List[Any]:
        ...

    @abstractmethod
    async def set_symbol_enabled(
        self,
        instrument_id: Optional[Union[int, str]] = None,
        enabled: bool = True,
        instrument: Optional[Union[int, str]] = None,
    ) -> Any:
        """Add to watchlist or update enabled flag."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...


class IDailyRiskRepository(ABC):
    """Abstract Port for Daily Risk tracking and circuit breaker limits."""

    @abstractmethod
    async def get(self, daily_risk_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_account_id(self, account_id: int, target_date: Optional[date] = None) -> Optional[Any]:
        """Fetch daily risk snapshot for an account."""
        ...

    @abstractmethod
    async def get_by_date(self, account_id: int, snapshot_date: date) -> Optional[Any]:
        """Fetch locked daily risk snapshot for an account and date."""
        ...

    @abstractmethod
    async def get_daily_snapshot(self, account_id: int, snapshot_date: date) -> Optional[Any]:
        """Alias for get_by_date."""
        ...

    @abstractmethod
    async def get_latest_snapshot(self, account_id: int) -> Optional[Any]:
        """Fetch most recent daily risk snapshot."""
        ...

    @abstractmethod
    async def get_or_create_daily_snapshot(self, schema: Any) -> Any:
        """Idempotent snapshot retrieval or creation."""
        ...

    @abstractmethod
    async def get_daily_history(self, account_id: int, start_date: date, end_date: date) -> List[Any]:
        """Fetch daily equity and risk snapshots within date range."""
        ...

    @abstractmethod
    async def get_remaining_risk_budget(self, daily_risk_id: int) -> Decimal:
        """Calculate remaining risk budget for the day in USDT."""
        ...

    @abstractmethod
    async def get_total_margin_used(self, daily_risk_id: int) -> Decimal:
        """Calculate total margin committed across all trades for the day."""
        ...

    async def get_or_create_daily_risk(self, account_id: int, target_date: Optional[date] = None) -> Any:
        return await self.get_by_account_id(account_id, target_date)

    async def add_realized_pnl(self, account_id: int, pnl_delta: Decimal, target_date: Optional[date] = None) -> Any:
        return await self.get_by_account_id(account_id, target_date)

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, daily_risk: Any) -> Any:
        ...


class ITradeRiskRepository(ABC):
    """Abstract Port for Trade Risk persistence and margin allocation."""

    @abstractmethod
    async def get_by_trade_id(self, trade_id: int) -> Optional[Any]:
        """Fetch risk parameters for a specific trade."""
        ...

    @abstractmethod
    async def get_total_active_risk_exposure(self, account_id: int) -> Decimal:
        """Calculate total USDT currently at risk across active trades."""
        ...

    @abstractmethod
    async def get_total_margin_used(self, account_id: int) -> Decimal:
        """Calculate total USDT margin locked in active positions."""
        ...

    @abstractmethod
    async def get_trade_risks_by_daily_config(self, daily_risk_id: int) -> List[Any]:
        """Fetch all trade risk allocations associated with a daily snapshot."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, trade_risk: Any) -> Any:
        ...


class IRiskProfileRepository(ABC):
    """Abstract Port for User Risk Profiles."""

    @abstractmethod
    async def get(self, profile_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_active_profile(self, user_id: Optional[int] = None) -> Optional[Any]:
        """Fetch the current active risk profile configuration."""
        ...

    @abstractmethod
    async def get_or_create_default_profile(self) -> Any:
        """Fetch active profile or create standard default profile."""
        ...

    @abstractmethod
    async def set_active_profile(self, profile_id: int) -> Optional[Any]:
        """Activate a profile and deactivate others."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...


class ISignalRepository(ABC):
    """Abstract Port for Trading Signal persistence and lifecycle."""

    @abstractmethod
    async def get(self, signal_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_telegram_message_id(self, message_id: int) -> Optional[Any]:
        """Fetch signal by its unique Telegram message ID."""
        ...

    @abstractmethod
    async def has_active_signal(self, instrument_id: int, side: str) -> bool:
        """Check if an active signal already exists for pair and side."""
        ...

    @abstractmethod
    async def get_pending_confirmation_signals(self) -> List[Any]:
        """Fetch signals awaiting manual confirmation."""
        ...

    @abstractmethod
    async def update_confirmation_status(self, signal_id: int, confirmation_status: str) -> Optional[Any]:
        """Update user confirmation status ('APPROVED' or 'REJECTED')."""
        ...

    @abstractmethod
    async def update_status(self, signal_id: int, status: str) -> Optional[Any]:
        """Update signal lifecycle status."""
        ...

    @abstractmethod
    async def get_signals_by_instrument(self, instrument_id: int, limit: int = 50) -> List[Any]:
        """Fetch recent signals for a specific trading pair."""
        ...

    @abstractmethod
    async def get_signals_paginated(
        self, page: int = 1, page_size: int = 20, status: Optional[str] = None
    ) -> Tuple[int, List[Any]]:
        """Fetch paginated signals feed with optional status filter."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, signal: Any) -> Any:
        ...


class ISignalProviderRepository(ABC):
    """Abstract Port for Signal Providers."""

    @abstractmethod
    async def get(self, provider_id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_type(self, provider_type: str = "TELEGRAM") -> List[Any]:
        """Fetch active signal providers by channel type."""
        ...

    @abstractmethod
    async def get_all_providers(self) -> List[Any]:
        """Fetch all signal providers."""
        ...

    async def get_active_providers(self) -> List[Any]:
        return await self.get_by_type("TELEGRAM")

    @abstractmethod
    async def get_provider_performance_summary(self, provider_id: int) -> Dict[str, Any]:
        """Aggregate total signals, win rate, and total net PnL."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...


class IStrategyRepository(ABC):
    """Abstract Port for Trading Strategies."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    async def get_by_code(self, code: str) -> Optional[Any]:
        return await self.get_by_name(code)

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Any]:
        """Fetch strategy by unique name."""
        ...

    @abstractmethod
    async def get_active_strategies(self) -> List[Any]:
        """Fetch all active strategies."""
        ...

    @abstractmethod
    async def get_all_strategies(self) -> List[Any]:
        """Fetch all strategies."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...


class ITradingAccountRepository(ABC):
    """Abstract Port for Trading Account credentials and environment routing."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_active_account(self, exchange_id: int = 1) -> Optional[Any]:
        """Fetch primary active account for an exchange."""
        ...

    @abstractmethod
    async def get_by_environment(self, environment: str = "MAINNET") -> List[Any]:
        """Fetch accounts by trading environment."""
        ...

    @abstractmethod
    async def get_account_with_credentials(self, account_id: int) -> Optional[Any]:
        """Fetch account with loaded API credentials."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...


class ITradingCredentialRepository(ABC):
    """Abstract Port for Encrypted API credentials."""

    @abstractmethod
    async def get_active_credential(self, account_id: int) -> Optional[Any]:
        """Fetch the active credential for a trading account."""
        ...

    @abstractmethod
    async def get_by_account_id(self, account_id: int) -> Optional[Any]:
        """Fetch active credential by account_id."""
        ...


    @abstractmethod
    async def deactivate_old_credentials(self, account_id: int) -> int:
        """Deactivate all active credentials for an account during rotation."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save_credential(self, credential: Any) -> Any:
        ...


class IExecutionRepository(ABC):
    """Abstract Port for Trade execution fill records."""

    @abstractmethod
    async def get_executions_by_trade_id(self, trade_id: int) -> List[Any]:
        """Fetch all execution fills for a trade."""
        ...

    @abstractmethod
    async def get_executions_by_order_id(self, order_id: int) -> List[Any]:
        """Fetch fills for a specific order."""
        ...

    @abstractmethod
    async def get_total_commission_by_trade(self, trade_id: int) -> Decimal:
        """Calculate total commissions paid for a trade."""
        ...

    @abstractmethod
    async def get_total_realized_pnl_by_trade(self, trade_id: int) -> Decimal:
        """Calculate cumulative realized PnL from closing fills."""
        ...

    async def get_by_trade_id(self, trade_id: int) -> List[Any]:
        return await self.get_executions_by_trade_id(trade_id)

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, execution: Any) -> Any:
        ...


class ITradeEventRepository(ABC):
    """Abstract Port for Trade lifecycle event audit timeline."""

    @abstractmethod
    async def log_event(
        self,
        trade_id: int,
        event_type: str,
        payload: Optional[Union[str, Dict[str, Any]]] = None,
        created_at: Optional[datetime] = None,
    ) -> Any:
        """Append an audit timeline event for a trade."""
        ...

    @abstractmethod
    async def get_events_by_trade(self, trade_id: int) -> List[Any]:
        """Fetch full timeline of events for a trade."""
        ...

    @abstractmethod
    async def get_latest_event_by_trade(self, trade_id: int) -> Optional[Any]:
        """Fetch most recent event for a trade."""
        ...

    @abstractmethod
    async def get_events_by_type(self, event_type: str, limit: int = 50) -> List[Any]:
        """Fetch recent events of a specific type across trades."""
        ...

    async def get_by_trade_id(self, trade_id: int) -> List[Any]:
        return await self.get_events_by_trade(trade_id)

    async def record_event(
        self, trade_id: int, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None
    ) -> Any:
        merged_payload = {"message": message, **(payload or {})}
        return await self.log_event(trade_id, event_type, merged_payload)


class ITradeSummaryRepository(ABC):
    """Abstract Port for Post-trade summary metrics and performance analytics."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        """Fetch trade summary by ID."""
        ...

    @abstractmethod
    async def get_by_trade_id(self, trade_id: int) -> Optional[Any]:
        """Fetch summary metrics for a specific trade."""
        ...

    @abstractmethod
    async def get_performance_summary(
        self,
        account_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Compute aggregate performance statistics (win rate, PnL, profit factor)."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...

    @abstractmethod
    async def save(self, summary: Any) -> Any:
        ...

    @abstractmethod
    async def get_daily_pnl_map(
        self,
        account_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[Any, float]:
        """Fetch daily realized PnL map grouped by date."""
        ...

    @abstractmethod
    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        account_id: Optional[int] = None,
    ) -> List[Any]:
        """Fetch multiple trade summary records."""
        ...


class IBotSettingRepository(ABC):
    """Abstract Port for Dynamic bot runtime parameters."""

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        """Create setting record."""
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        """Update setting record."""
        ...


    @abstractmethod
    async def get_by_key(self, key: str) -> Optional[Any]:
        """Fetch setting record by unique key."""
        ...

    @abstractmethod
    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        ...

    @abstractmethod
    async def get_bool(self, key: str, default: bool = False) -> bool:
        ...

    @abstractmethod
    async def get_int(self, key: str, default: int = 0) -> int:
        ...

    @abstractmethod
    async def get_float(self, key: str, default: float = 0.0) -> float:
        ...

    @abstractmethod
    async def get_json(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        ...

    @abstractmethod
    async def set_value(
        self,
        key: str,
        value: str,
        category: str = "GENERAL",
        setting_type: str = "STRING",
        description: Optional[str] = None,
    ) -> Any:
        """Upsert setting value."""
        ...

    @abstractmethod
    async def get_all_by_category(self, category: str) -> List[Any]:
        ...

    @abstractmethod
    async def get_all_as_dict(self) -> Dict[str, str]:
        ...

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return await self.get_value(key, default)

    async def set_setting(self, key: str, value: str) -> Any:
        return await self.set_value(key, value)


class IBotLogRepository(ABC):
    """Abstract Port for System audit and operational logs."""

    @abstractmethod
    async def create_log(
        self,
        level: str,
        message: str,
        module: Optional[str] = None,
        context: Optional[Union[str, Dict[str, Any]]] = None,
        created_at: Optional[datetime] = None,
    ) -> Any:
        """Create and persist an audit log record."""
        ...

    @abstractmethod
    async def get_recent_logs(
        self, limit: int = 100, level: Optional[str] = None, module: Optional[str] = None
    ) -> List[Any]:
        """Fetch recent system logs."""
        ...

    @abstractmethod
    async def query_logs(
        self, level: Optional[str] = None, trace_id: Optional[str] = None, limit: int = 100
    ) -> List[Any]:
        """Query audit logs with optional level and trace_id filters."""
        ...

    @abstractmethod
    async def get_error_logs(self, limit: int = 50, start_date: Optional[datetime] = None) -> List[Any]:
        """Fetch recent ERROR and CRITICAL logs."""
        ...

    @abstractmethod
    async def get_recent_errors(self, limit: int = 5) -> List[Any]:
        ...

    @abstractmethod
    async def purge_old_logs(self, days: int = 30) -> int:
        """Purge logs older than retention days."""
        ...

    async def log(self, level: str, module: str, message: str, details: Optional[Dict[str, Any]] = None) -> Any:
        return await self.create_log(level=level, message=message, module=module, context=details)


class IUserRepository(ABC):
    """Abstract Port for User authentication and admin profiles."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[Any]:
        """Fetch user by unique username."""
        ...

    @abstractmethod
    async def create_user(
        self, username: str, password_hash: str, role: str = "ADMIN", is_active: bool = True
    ) -> Any:
        """Create and persist a new user account."""
        ...

    @abstractmethod
    async def update_password(self, user_id: int, new_password_hash: str) -> Optional[Any]:
        """Update password hash for an existing user."""
        ...

    @abstractmethod
    async def ensure_default_admin(self, default_username: str, default_password_hash: str) -> Any:
        """Seed a default admin user if no users exist."""
        ...


class IExchangeRepository(ABC):
    """Abstract Port for Exchange master entity access."""

    @abstractmethod
    async def get(self, id: int) -> Optional[Any]:
        ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Optional[Any]:
        """Fetch an exchange by unique code."""
        ...

    @abstractmethod
    async def get_active_exchanges(self) -> List[Any]:
        """Fetch all exchanges with active status."""
        ...

    @abstractmethod
    async def toggle_status(self, id: int, status: bool) -> Optional[Any]:
        """Enable or disable an exchange."""
        ...

    @abstractmethod
    async def create(self, schema: Any) -> Any:
        ...

    @abstractmethod
    async def update(self, db_obj: Any, schema: Any) -> Any:
        ...
