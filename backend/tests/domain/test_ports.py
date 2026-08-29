"""Unit tests for domain port contracts (interfaces)."""

from decimal import Decimal
import pytest
from src.domain.ports.repositories import (
    ITradeRepository,
    IOrderRepository,
    IInstrumentRepository,
    IInstrumentLeverageBracketRepository,
    IWatchlistRepository,
    IDailyRiskRepository,
    IRiskProfileRepository,
    ISignalRepository,
    ISignalProviderRepository,
    IStrategyRepository,
    ITradingAccountRepository,
    ITradingCredentialRepository,
    IExecutionRepository,
    ITradeEventRepository,
    ITradeSummaryRepository,
    IBotSettingRepository,
    IBotLogRepository,
    IUserRepository,
)
from src.domain.ports.gateways import (
    IExchangeGateway,
    INotificationGateway,
)
from src.domain.ports.event_publisher import IDomainEventPublisher


def test_cannot_instantiate_abstract_ports():
    """Verify that ABC port contracts cannot be instantiated directly without concrete implementations."""
    with pytest.raises(TypeError):
        ITradeRepository()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        IOrderRepository()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        IExchangeGateway()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        INotificationGateway()  # type: ignore[abstract]

    with pytest.raises(TypeError):
        IDomainEventPublisher()  # type: ignore[abstract]


def test_concrete_mock_implementation_of_port():
    """Verify a concrete mock repository properly satisfies the interface contract."""

    class MockTradeRepo(ITradeRepository):
        async def get(self, trade_id: int): return {"id": trade_id}
        async def get_by_id(self, trade_id: int): return {"id": trade_id}
        async def get_detail(self, trade_id: int): return {"id": trade_id}
        async def get_with_instrument(self, trade_id: int): return {"id": trade_id}
        async def get_active_trade_by_instrument(self, instrument_id: int): return None
        async def get_active_trade_by_symbol(self, symbol: str, account_id=None): return None
        async def count_active_trades(self, account_id: int): return 0
        async def count_open_positions(self, account_id=None): return 0
        async def get_all_active_trades(self, account_id=None): return []
        async def get_active_trades(self, account_id=None): return []
        async def get_active_trades_with_instrument(self, account_id=None): return []
        async def get_expired_waiting_trades(self, max_hours=4): return []
        async def update_entry_fill(self, trade_id, entry_price, avg_entry_price=None, opened_at=None): return None
        async def update_sl_price(self, trade_id, new_sl_price): return None
        async def update_stop_loss(self, trade_id, new_sl_price): return None
        async def reduce_position_qty(self, trade_id, closed_qty, is_closed=False): return None
        async def update_partial_close(self, trade_id, closed_qty, remaining_qty, realized_pnl): return None
        async def update_trade_status(self, trade_id, schema): return None
        async def get_closed_trades_history(self, account_id, skip=0, limit=50, start_date=None, end_date=None): return []
        async def get_active_positions_with_relations(self, account_id: int): return []
        async def get_history_paginated(self, account_id, page=1, page_size=20, symbol=None, result=None, start_date=None, end_date=None): return 0, []
        async def get_closed_trades_for_report(self, start_date=None, end_date=None): return []
        async def create(self, schema): return schema
        async def update(self, db_obj, schema): return db_obj
        async def save(self, trade): return trade

    repo = MockTradeRepo()
    assert repo is not None


def test_concrete_mock_exchange_gateway_satisfies_contract():
    """Verify a mock exchange gateway satisfies IExchangeGateway interface."""

    class MockExchange(IExchangeGateway):
        async def get_balance(self): return {}
        async def fetch_balance(self): return {}
        async def fetch_ticker(self, symbol): return {}
        async def fetch_ticker_price(self, symbol): return Decimal("50000")
        async def fetch_klines(self, symbol, timeframe="1m", since=None, limit=30): return []
        async def has_price_reached_target(self, symbol, target_price, side, since_timestamp_ms=None, limit=30): return False
        async def set_leverage(self, symbol, leverage): return {}
        async def set_margin_mode(self, symbol, margin_mode): return {}
        async def set_position_mode(self, dual_side_position=False): return {}
        async def create_order(self, symbol, side, order_type, qty, price=None, stop_price=None, client_order_id=None, params=None): return {}
        async def create_entry_order(self, symbol, side, order_type, qty, price=None, client_order_id=None, reduce_only=False): return {}
        async def create_stop_loss_order(self, symbol, side, stop_price, qty=None, client_order_id=None, close_position=True, working_type="MARK_PRICE"): return {}
        async def create_take_profit_order(self, symbol, side, tp_price, qty, client_order_id=None, working_type="MARK_PRICE"): return {}
        async def cancel_order(self, symbol, exchange_order_id=None, client_order_id=None): return {}
        async def cancel_all_orders(self, symbol): return []
        async def cancel_all_open_orders(self, symbol): return []
        async def fetch_open_orders(self, symbol=None): return []
        async def fetch_order(self, symbol, order_id): return None
        async def fetch_positions(self, symbol=None): return []
        async def fetch_leverage_brackets(self, symbol=None): return []
        async def fetch_instruments_metadata(self): return []
        def reconfigure(self, api_key=None, secret_key=None, testnet=None): pass
        async def close(self): pass

    gw = MockExchange()
    assert gw is not None


def test_concrete_mock_notification_gateway_satisfies_contract():
    """Verify a mock notification gateway satisfies INotificationGateway interface."""

    class MockNotification(INotificationGateway):
        async def send_message(self, text, chat_id=None, parse_mode="HTML", reply_markup=None): return {}
        async def send_alert(self, title, message, level="INFO", chat_id=None): return {}
        async def send_signal_confirmation(self, chat_id=None, signal_id=None, symbol=None, side=None, entry_range=None, sl=None, tp_targets=None, confidence=None, text=None, reply_markup=None): return {}
        async def send_trade_opened_alert(self, chat_id=None, **kwargs): return {}
        async def send_take_profit_alert(self, chat_id=None, **kwargs): return {}
        async def send_stop_loss_moved_alert(self, chat_id=None, **kwargs): return {}
        async def send_trade_closed_alert(self, chat_id=None, **kwargs): return {}
        async def send_panic_close_alert(self, chat_id=None, **kwargs): return {}
        async def send_circuit_breaker_alert(self, chat_id=None, **kwargs): return {}
        async def send_signal_rejected_alert(self, chat_id=None, **kwargs): return {}
        async def send_price_runaway_alert(self, chat_id=None, **kwargs): return {}
        async def send_daily_summary_alert(self, chat_id=None, **kwargs): return {}
        async def edit_message_text(self, chat_id, message_id, text, parse_mode="HTML", reply_markup=None): return {}
        async def answer_callback_query(self, callback_query_id, text=None, show_alert=False): return {}
        async def set_my_commands(self, commands=None): return {}
        async def close(self): pass

    ngw = MockNotification()
    assert ngw is not None


def test_binance_exchange_adapter_satisfies_port():
    """Verify concrete BinanceExchangeAdapter satisfies IExchangeGateway."""
    from unittest.mock import MagicMock
    from src.infrastructure.gateways.binance.binance_adapter import BinanceExchangeAdapter
    from src.infrastructure.gateways.binance.binance_connector import BinanceConnector

    mock_conn = MagicMock(spec=BinanceConnector)
    adapter = BinanceExchangeAdapter(connector=mock_conn)
    assert isinstance(adapter, IExchangeGateway)
    assert getattr(adapter, "__abstractmethods__", set()) == set()


def test_telegram_notification_adapter_satisfies_port():
    """Verify concrete TelegramNotificationAdapter satisfies INotificationGateway."""
    from unittest.mock import MagicMock
    from src.infrastructure.gateways.telegram.telegram_adapter import TelegramNotificationAdapter
    from src.infrastructure.gateways.telegram.telegram_connector import TelegramConnector

    mock_conn = MagicMock(spec=TelegramConnector)
    adapter = TelegramNotificationAdapter(connector=mock_conn)
    assert isinstance(adapter, INotificationGateway)
    assert getattr(adapter, "__abstractmethods__", set()) == set()
