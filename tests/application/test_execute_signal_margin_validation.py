"""Integration tests for ExecuteSignalUseCase pre-trade margin validation and error handling."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.dto.trade_commands import ExecuteSignalCommand
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions import InsufficientMarginRiskError, InsufficientMarginError
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

    instrument_repo.get_by_symbol = AsyncMock()
    watchlist_repo.is_symbol_enabled = AsyncMock(return_value=True)
    trade_repo.get_active_trade_by_instrument = AsyncMock(return_value=None)
    trade_repo.get_all_active_trades = AsyncMock(return_value=[])
    trade_repo.create = AsyncMock()
    trade_repo.update_entry_fill = AsyncMock()
    trade_repo.update_trade_status = AsyncMock()
    
    mock_snap = MagicMock(id=1, balance=Decimal("10000.0"), risk_amount=Decimal("200.0"), daily_risk_amount=Decimal("500.0"))
    daily_risk_repo.get_by_date.return_value = mock_snap
    daily_risk_repo.get_or_create_daily_snapshot.return_value = mock_snap
    daily_risk_repo.get_remaining_risk_budget.return_value = Decimal("200.0")
    
    order_repo.create = AsyncMock()
    trade_event_repo.log_event = AsyncMock()
    risk_profile_repo.get_or_create_default_profile = AsyncMock(
        return_value=MagicMock(id=1, risk_percent=Decimal("2.0"), max_open_trade=3, max_daily_loss=Decimal("5.0"))
    )
    
    exchange_gateway.fetch_balance = AsyncMock()
    exchange_gateway.fetch_ticker = AsyncMock()
    exchange_gateway.set_leverage = AsyncMock()
    exchange_gateway.set_margin_mode = AsyncMock()
    exchange_gateway.create_order = AsyncMock()
    exchange_gateway.has_price_reached_target = AsyncMock(return_value=False)
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
async def test_execute_signal_with_auto_margin_capping(mock_deps):
    """When required margin exceeds free margin, lot is auto-capped and successfully placed."""
    deps = mock_deps
    mock_inst = MagicMock(
        id=1,
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        min_qty=Decimal("0.001"),
        price_precision=2,
        qty_precision=3,
    )
    deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    
    # Total balance $10,000 (risk $200), Free margin $20
    # Entry 50,000, SL 49,000 (Dist 1000). Raw qty = 200 / 1000 = 0.200 BTC.
    # Raw notional = 0.2 * 50,000 = 10,000 USDT. Required margin @ 10x = 1000 USDT > 20 USDT.
    # Capped margin (95% of $20) = $19 -> Notional = $190 -> Capped qty = 190 / 50000 = 0.003 BTC.
    deps["exchange_gateway"].fetch_balance.return_value = {
        "total_wallet_balance": Decimal("10000.0"),
        "free_margin": Decimal("20.0"),
    }
    deps["exchange_gateway"].fetch_ticker.return_value = {"last_price": Decimal("50000.0")}
    deps["exchange_gateway"].create_order.return_value = {
        "id": "BIN_ENTRY_CAPPED_1",
        "average": Decimal("50000.0"),
        "status": "FILLED",
    }

    mock_trade = MagicMock(id=1, status="OPEN")
    deps["trade_repo"].create.return_value = mock_trade
    deps["trade_repo"].update_entry_fill.return_value = mock_trade

    use_case = ExecuteSignalUseCase(
        instrument_repo=deps["instrument_repo"],
        watchlist_repo=deps["watchlist_repo"],
        trade_repo=deps["trade_repo"],
        trade_risk_repo=deps["trade_risk_repo"],
        daily_risk_repo=deps["daily_risk_repo"],
        order_repo=deps["order_repo"],
        trade_event_repo=deps["trade_event_repo"],
        risk_profile_repo=deps["risk_profile_repo"],
        bracket_repo=None,
        exchange_gateway=deps["exchange_gateway"],
        event_publisher=deps["event_publisher"],
    )

    sig = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        tp_targets=[Decimal("52000.0")],
        leverage=10,
        is_valid=True,
        raw_text="BUY BTCUSDT 50000 SL 49000",
    )

    cmd = ExecuteSignalCommand(
        signal_dto=sig,
        account_id=1,
    )

    res = await use_case.execute(cmd)
    assert res.is_success is True
    assert res.status in ("OPEN", "EXECUTED")
    # Position size should be auto-capped to 0.003 BTC
    assert res.position_size == Decimal("0.003")


@pytest.mark.asyncio
async def test_execute_signal_insufficient_margin_raises_detailed_error(mock_deps, monkeypatch):
    """When auto margin capping is disabled, insufficient margin raises InsufficientMarginRiskError."""
    from config.settings import settings
    monkeypatch.setattr(settings, "AUTO_MARGIN_CAPPING", False)

    deps = mock_deps
    mock_inst = MagicMock(
        id=1,
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        min_qty=Decimal("0.001"),
        price_precision=2,
        qty_precision=3,
    )
    deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    deps["exchange_gateway"].fetch_balance.return_value = {
        "total_wallet_balance": Decimal("10000.0"),
        "free_margin": Decimal("20.0"),
    }
    deps["exchange_gateway"].fetch_ticker.return_value = {"last_price": Decimal("50000.0")}

    use_case = ExecuteSignalUseCase(
        instrument_repo=deps["instrument_repo"],
        watchlist_repo=deps["watchlist_repo"],
        trade_repo=deps["trade_repo"],
        trade_risk_repo=deps["trade_risk_repo"],
        daily_risk_repo=deps["daily_risk_repo"],
        order_repo=deps["order_repo"],
        trade_event_repo=deps["trade_event_repo"],
        risk_profile_repo=deps["risk_profile_repo"],
        bracket_repo=None,
        exchange_gateway=deps["exchange_gateway"],
        event_publisher=deps["event_publisher"],
    )

    sig = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        tp_targets=[Decimal("52000.0")],
        leverage=10,
        is_valid=True,
        raw_text="BUY BTCUSDT 50000 SL 49000",
    )

    cmd = ExecuteSignalCommand(
        signal_dto=sig,
        account_id=1,
    )

    with pytest.raises(InsufficientMarginRiskError) as exc_info:
        await use_case.execute(cmd)

    err = exc_info.value
    assert err.available_margin == Decimal("20.0")
    assert err.required_margin == Decimal("1000.000")
    assert Decimal(str(err.shortfall)) == Decimal("980.000")


@pytest.mark.asyncio
async def test_execute_signal_exchange_insufficient_margin_wrapped(mock_deps):
    """When Binance throws InsufficientMarginError during create_order, it is wrapped in InsufficientMarginRiskError."""
    deps = mock_deps
    mock_inst = MagicMock(
        id=1,
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        min_qty=Decimal("0.001"),
        price_precision=2,
        qty_precision=3,
    )
    deps["instrument_repo"].get_by_symbol.return_value = mock_inst
    deps["exchange_gateway"].fetch_balance.return_value = {
        "total_wallet_balance": Decimal("10000.0"),
        "free_margin": Decimal("10000.0"),
    }
    deps["exchange_gateway"].fetch_ticker.return_value = {"last_price": Decimal("50000.0")}
    deps["exchange_gateway"].create_order.side_effect = InsufficientMarginError("binanceusdm Margin is insufficient.")

    mock_trade = MagicMock(id=1, status="OPEN")
    deps["trade_repo"].create.return_value = mock_trade

    use_case = ExecuteSignalUseCase(
        instrument_repo=deps["instrument_repo"],
        watchlist_repo=deps["watchlist_repo"],
        trade_repo=deps["trade_repo"],
        trade_risk_repo=deps["trade_risk_repo"],
        daily_risk_repo=deps["daily_risk_repo"],
        order_repo=deps["order_repo"],
        trade_event_repo=deps["trade_event_repo"],
        risk_profile_repo=deps["risk_profile_repo"],
        bracket_repo=None,
        exchange_gateway=deps["exchange_gateway"],
        event_publisher=deps["event_publisher"],
    )

    sig = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        tp_targets=[Decimal("52000.0")],
        leverage=10,
        is_valid=True,
        raw_text="BUY BTCUSDT 50000 SL 49000",
    )

    cmd = ExecuteSignalCommand(
        signal_dto=sig,
        account_id=1,
    )

    with pytest.raises(InsufficientMarginError) as exc_info:
        await use_case.execute(cmd)

    assert "Margin is insufficient" in str(exc_info.value)
