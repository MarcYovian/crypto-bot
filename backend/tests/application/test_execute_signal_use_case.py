"""Unit tests for ExecuteSignalUseCase end-to-end orchestration."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.dto.trade_commands import ExecuteSignalCommand
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.exceptions import (
    DailyRiskLimitReachedError,
    MaxRiskExceededError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
)
from src.domain.ports.event_publisher import IDomainEventPublisher
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IInstrumentRepository,
    IOrderRepository,
    IRiskProfileRepository,
    ITradeEventRepository,
    ITradeRepository,
    ITradeRiskRepository,
    IWatchlistRepository,
)
from src.domain.entities.signal import ParsedSignalDTO


@pytest.fixture
def mock_deps():
    instrument_repo = MagicMock(spec=IInstrumentRepository)
    watchlist_repo = MagicMock(spec=IWatchlistRepository)
    trade_repo = MagicMock(spec=ITradeRepository)
    trade_risk_repo = MagicMock(spec=ITradeRiskRepository)
    daily_risk_repo = MagicMock(spec=IDailyRiskRepository)
    order_repo = MagicMock(spec=IOrderRepository)
    trade_event_repo = MagicMock(spec=ITradeEventRepository)
    risk_profile_repo = MagicMock(spec=IRiskProfileRepository)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    event_publisher = MagicMock(spec=IDomainEventPublisher)

    # Set async mock methods
    instrument_repo.get_by_symbol = AsyncMock()
    watchlist_repo.is_symbol_enabled = AsyncMock()
    trade_repo.get_active_trade_by_instrument = AsyncMock()
    trade_repo.get_all_active_trades = AsyncMock()
    trade_repo.create = AsyncMock()
    trade_repo.update_entry_fill = AsyncMock()
    mock_snap = MagicMock(id=1, balance=Decimal("10000.0"), risk_amount=Decimal("200.0"), daily_risk_amount=Decimal("500.0"))
    daily_risk_repo.get_by_date.return_value = mock_snap
    daily_risk_repo.get_or_create_daily_snapshot.return_value = mock_snap
    daily_risk_repo.get_remaining_risk_budget.return_value = Decimal("200.0")
    order_repo.create = AsyncMock()
    trade_event_repo.log_event = AsyncMock()
    risk_profile_repo.get_or_create_default_profile = AsyncMock()
    exchange_gateway.fetch_balance = AsyncMock()
    exchange_gateway.fetch_ticker = AsyncMock()
    exchange_gateway.set_leverage = AsyncMock()
    exchange_gateway.set_margin_mode = AsyncMock()
    exchange_gateway.create_order = AsyncMock()
    event_publisher.publish = AsyncMock()

    return {
        "instrument_repo": instrument_repo,
        "watchlist_repo": watchlist_repo,
        "trade_repo": trade_repo,
        "trade_risk_repo": trade_risk_repo,
        "daily_risk_repo": daily_risk_repo,
        "order_repo": order_repo,
        "trade_event_repo": trade_event_repo,
        "risk_profile_repo": risk_profile_repo,
        "exchange_gateway": exchange_gateway,
        "event_publisher": event_publisher,
    }


@pytest.mark.asyncio
async def test_execute_signal_market_success(mock_deps):
    # Setup Instrument & Watchlist
    mock_inst = MagicMock()
    mock_inst.id = 1
    mock_inst.symbol = "BTCUSDT"
    mock_inst.tick_size = Decimal("0.1")
    mock_inst.step_size = Decimal("0.001")
    mock_inst.price_precision = 2
    mock_inst.qty_precision = 3
    mock_inst.min_notional = Decimal("5.0")
    mock_deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    mock_deps["watchlist_repo"].is_symbol_enabled.return_value = True

    # No duplicate trade
    mock_deps["trade_repo"].get_active_trade_by_instrument.return_value = None
    mock_deps["trade_repo"].get_all_active_trades.return_value = []

    # Risk profile & balance
    mock_profile = MagicMock()
    mock_profile.id = 1
    mock_profile.risk_percent = Decimal("2.0")
    mock_profile.max_open_trade = 3
    mock_deps["risk_profile_repo"].get_or_create_default_profile.return_value = mock_profile

    mock_deps["exchange_gateway"].fetch_balance.return_value = {
        "free_margin": Decimal("10000.0"),
        "total_wallet_balance": Decimal("10000.0"),
    }
    mock_deps["daily_risk_repo"].get_by_date.return_value = MagicMock(id=1, balance=Decimal("10000.0"))
    mock_deps["daily_risk_repo"].get_remaining_risk_budget.return_value = Decimal("200.0")

    # Current price close to target entry (deviasi 0.0%) -> MARKET
    mock_deps["exchange_gateway"].fetch_ticker.return_value = {"symbol": "BTCUSDT", "last_price": Decimal("65000.0")}
    mock_deps["exchange_gateway"].create_order.return_value = {
        "exchange_order_id": "123456",
        "average": Decimal("65000.0"),
    }

    mock_trade = MagicMock(id=101, status="OPEN", side="BUY", remaining_qty=Decimal("0.1"))
    mock_deps["trade_repo"].create.return_value = mock_trade
    mock_deps["trade_repo"].update_entry_fill.return_value = mock_trade

    use_case = ExecuteSignalUseCase(**mock_deps)

    sig_dto = ParsedSignalDTO(
        raw_text="BTCUSDT BUY",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("65000.0"),
        sl_price=Decimal("63000.0"),
        tp_targets=[Decimal("67000.0"), Decimal("70000.0")],
        leverage=10,
        is_valid=True,
    )

    result = await use_case.execute(ExecuteSignalCommand(signal_dto=sig_dto))

    assert result.is_success is True
    assert result.status == "OPEN"
    assert result.trade_id == 101
    mock_deps["exchange_gateway"].set_leverage.assert_awaited_once_with("BTCUSDT", 10)
    mock_deps["event_publisher"].publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_signal_tp1_already_hit_rejection(mock_deps):
    mock_inst = MagicMock(id=1, symbol="BTCUSDT", tick_size=Decimal("0.1"), price_precision=2)
    mock_deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    mock_deps["watchlist_repo"].is_symbol_enabled.return_value = True
    mock_deps["trade_repo"].get_active_trade_by_instrument.return_value = None
    mock_deps["trade_repo"].get_all_active_trades.return_value = []
    mock_deps["risk_profile_repo"].get_or_create_default_profile.return_value = MagicMock(max_open_trade=3)
    mock_deps["exchange_gateway"].fetch_balance.return_value = {"free_margin": Decimal("10000.0")}
    mock_deps["daily_risk_repo"].get_by_date.return_value = MagicMock(id=1)
    mock_deps["daily_risk_repo"].get_remaining_risk_budget.return_value = Decimal("200.0")

    # Current price 68000 >= TP1 (67000) for BUY
    mock_deps["exchange_gateway"].fetch_ticker.return_value = {"symbol": "BTCUSDT", "last_price": Decimal("68000.0")}

    use_case = ExecuteSignalUseCase(**mock_deps)

    sig_dto = ParsedSignalDTO(
        raw_text="BTCUSDT BUY",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("65000.0"),
        sl_price=Decimal("63000.0"),
        tp_targets=[Decimal("67000.0")],
        is_valid=True,
    )

    result = await use_case.execute(ExecuteSignalCommand(signal_dto=sig_dto))

    assert result.is_success is False
    assert result.status == "REJECTED"
    assert "already passed TP1" in result.message
    mock_deps["exchange_gateway"].create_order.assert_not_called()


@pytest.mark.asyncio
async def test_execute_signal_circuit_breaker_active(mock_deps):
    mock_inst = MagicMock(id=1, symbol="BTCUSDT", tick_size=Decimal("0.1"), price_precision=2)
    mock_deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    mock_deps["watchlist_repo"].is_symbol_enabled.return_value = True
    mock_deps["trade_repo"].get_active_trade_by_instrument.return_value = None
    mock_deps["trade_repo"].get_all_active_trades.return_value = []
    mock_deps["risk_profile_repo"].get_or_create_default_profile.return_value = MagicMock(max_open_trade=3)
    mock_deps["exchange_gateway"].fetch_balance.return_value = {"free_margin": Decimal("10000.0")}

    # Remaining daily risk is 0 USDT (Circuit Breaker)
    mock_deps["daily_risk_repo"].get_by_date.return_value = MagicMock(id=1)
    mock_deps["daily_risk_repo"].get_remaining_risk_budget.return_value = Decimal("0.0")

    use_case = ExecuteSignalUseCase(**mock_deps)

    sig_dto = ParsedSignalDTO(
        raw_text="BTCUSDT BUY",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("65000.0"),
        sl_price=Decimal("63000.0"),
        tp_targets=[Decimal("67000.0")],
        is_valid=True,
    )

    with pytest.raises(DailyRiskLimitReachedError):
        await use_case.execute(ExecuteSignalCommand(signal_dto=sig_dto))
