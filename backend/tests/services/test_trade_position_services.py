"""Comprehensive unit tests for TradeService and PositionManager."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, Trade, Order, Execution, TradeEvent, TradeSummary, DailyRiskConfig
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, InstrumentLeverageBracketCreate
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.entities.trade import OrderFillDTO
from src.domain.exceptions.trade import (
    TradeExecutionError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
)
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.risk_calculator import RiskCalculatorService

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create a fresh in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def setup_env(async_session: AsyncSession):
    """Seed test Exchange, Account, Instrument, and Watchlist."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="MAINNET",
        is_active=True,
    ))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True,
    ))
    watchlist = await watch_repo.create(WatchlistCreate(
        account_id=account.id,
        instrument_id=instrument.id,
        is_enabled=True,
        max_leverage=20,
    ))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": instrument,
        "watchlist": watchlist,
    }


@pytest.mark.asyncio
async def test_trade_service_execute_signal_full_success(async_session: AsyncSession, setup_env: dict):
    """Test full execution pipeline from ParsedSignalDTO to Trade and Order creation."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    # Mock Binance client
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 20})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        binance_client=mock_binance,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000, 64000, 66000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        entry_targets=[Decimal("60000")],
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000"), Decimal("64000"), Decimal("66000")],
        leverage=20,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.symbol == "BTCUSDT"
    assert res.position_size == Decimal("0.100")
    assert res.trade_id is not None

    # Verify orders in DB
    order_repo = OrderRepository(async_session)
    orders = await order_repo.get_orders_by_trade_id(res.trade_id)
    assert len(orders) == 5  # 1 Entry + 1 SL + 3 TPs

    purposes = {o.purpose for o in orders}
    assert "ENTRY" in purposes
    assert "SL" in purposes
    assert "TP1" in purposes
    assert "TP2" in purposes
    assert "TP3" in purposes


@pytest.mark.asyncio
async def test_trade_service_reject_unwhitelisted_symbol(async_session: AsyncSession, setup_env: dict):
    """Test rejecting signals for symbols not in active watchlist."""
    acc = setup_env["account"]

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    signal = ParsedSignalDTO(
        raw_text="BUY ETHUSDT Entry: 3000 SL: 2900 TP: 3200",
        symbol="ETHUSDT",  # Not seeded in setup
        side="BUY",
        entry_min=Decimal("3000"),
        entry_max=Decimal("3000"),
        sl_price=Decimal("2900"),
        tp_targets=[Decimal("3200")],
    )

    with pytest.raises(SymbolNotWhitelistedError):
        await trade_service.execute_signal(signal, account_id=acc.id)


@pytest.mark.asyncio
async def test_trade_service_reject_when_pair_already_active(async_session: AsyncSession, setup_env: dict):
    """Test preventing duplicate trades on the same symbol."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    trade_repo = TradeRepository(async_session)
    # Seed an open trade
    from src.schemas.trade import TradeCreate
    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        sl_price=Decimal("58000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        sl_price=Decimal("58000"),
        tp_targets=[Decimal("62000")],
    )

    with pytest.raises(PairAlreadyActiveError):
        await trade_service.execute_signal(signal, account_id=acc.id)


@pytest.mark.asyncio
async def test_position_manager_handle_entry_fill_opens_trade(async_session: AsyncSession, setup_env: dict):
    """Test entry fill event updating trade status to OPEN."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    from src.schemas.trade import TradeCreate
    from src.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("58000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="BUY",
        order_type="LIMIT",
        purpose="ENTRY",
        price=Decimal("60000"),
        qty=Decimal("0.1"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_event = OrderFillDTO(
        order_id=order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="BUY",
        purpose="ENTRY",
        fill_price=Decimal("60000.0"),
        fill_qty=Decimal("0.1"),
        fee=Decimal("1.50"),
    )

    await pos_manager.handle_order_fill(fill_event)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "OPEN"
    assert updated_trade.entry_price == Decimal("60000.0")


@pytest.mark.asyncio
async def test_position_manager_handle_tp1_fill_moves_sl_to_bep(async_session: AsyncSession, setup_env: dict):
    """Test TP1 fill triggering Break-Even Protection (moving SL to entry price)."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    event_repo = TradeEventRepository(async_session)

    from src.schemas.trade import TradeCreate
    from src.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    # Old SL order
    old_sl = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="STOP_MARKET",
        purpose="SL",
        price=Decimal("58000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    # TP1 order
    tp1_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP1",
        price=Decimal("62000.0"),
        qty=Decimal("0.050"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=event_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_tp1 = OrderFillDTO(
        order_id=tp1_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="TP1",
        fill_price=Decimal("62000.0"),
        fill_qty=Decimal("0.050"),
        fee=Decimal("0.75"),
        realized_pnl=Decimal("100.0"),
    )

    await pos_manager.handle_order_fill(fill_tp1)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.sl_price == Decimal("60000.0")  # SL moved to entry
    assert updated_trade.remaining_qty == Decimal("0.050")

    events = await event_repo.get_events_by_trade(trade.id)
    event_types = [e.event_type for e in events]
    assert "TP1_HIT" in event_types
    assert "SL_MOVED_TO_BEP" in event_types


@pytest.mark.asyncio
async def test_position_manager_handle_tp2_fill_updates_trailing_sl(async_session: AsyncSession, setup_env: dict):
    """Test TP2 fill moving SL to TP1 level (Trailing Stop)."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    event_repo = TradeEventRepository(async_session)

    from src.schemas.trade import TradeCreate
    from src.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="PARTIAL",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("60000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.050"),
    ))

    # TP1 order
    await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP1",
        price=Decimal("62000.0"),
        qty=Decimal("0.050"),
        status="FILLED",
    ))

    # TP2 order
    tp2_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="LIMIT",
        purpose="TP2",
        price=Decimal("64000.0"),
        qty=Decimal("0.030"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=event_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_tp2 = OrderFillDTO(
        order_id=tp2_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="TP2",
        fill_price=Decimal("64000.0"),
        fill_qty=Decimal("0.030"),
        fee=Decimal("0.50"),
        realized_pnl=Decimal("120.0"),
    )

    await pos_manager.handle_order_fill(fill_tp2)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.sl_price == Decimal("62000.0")  # SL moved to TP1
    assert updated_trade.remaining_qty == Decimal("0.020")


@pytest.mark.asyncio
async def test_position_manager_handle_sl_fill_finalizes_summary_loss(async_session: AsyncSession, setup_env: dict):
    """Test SL fill finalizing trade, generating TradeSummary with LOSS, and closing trade."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)
    exec_repo = ExecutionRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    from src.schemas.trade import TradeCreate
    from src.schemas.order import OrderCreate

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        initial_risk_usdt=Decimal("200.0"),
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
        leverage=20,
    ))

    sl_order = await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="SELL",
        order_type="STOP_MARKET",
        purpose="SL",
        price=Decimal("58000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=exec_repo,
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=sum_repo,
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    fill_sl = OrderFillDTO(
        order_id=sl_order.id,
        trade_id=trade.id,
        symbol="BTCUSDT",
        side="SELL",
        purpose="SL",
        fill_price=Decimal("58000.0"),
        fill_qty=Decimal("0.100"),
        fee=Decimal("2.0"),
        realized_pnl=Decimal("-200.0"),
    )

    await pos_manager.handle_order_fill(fill_sl)

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"

    summary = await sum_repo.get_by_trade_id(trade.id)
    assert summary is not None
    assert summary.result == "LOSS"
    assert summary.net_pnl == Decimal("-202.0")  # -200 PnL - 2 fee
    assert summary.close_reason == "SL_HIT"


@pytest.mark.asyncio
async def test_trade_service_close_trade_manually(async_session: AsyncSession, setup_env: dict):
    """Test manual closure of active trade via TradeService."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    from src.schemas.trade import TradeCreate
    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=trade_repo,
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
    )

    closed = await trade_service.close_trade_manually(trade.id)
    assert closed is True

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"


@pytest.mark.asyncio
async def test_trade_service_dynamic_leverage_execution(async_session: AsyncSession, setup_env: dict):
    """Test trade execution end-to-end with dynamic leverage downscaling and bracket lookup."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]

    # Seed leverage brackets for BTCUSDT (Tier 1: Max 50x, Tier 2: Max 20x)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)
    await bracket_repo.bulk_upsert_brackets(
        inst.id,
        [
            InstrumentLeverageBracketCreate(
                instrument_id=inst.id,
                bracket=1,
                initial_leverage=50,
                notional_floor=Decimal("0"),
                notional_cap=Decimal("50000"),
                maint_margin_ratio=Decimal("0.01"),
                cum=Decimal("0"),
            ),
            InstrumentLeverageBracketCreate(
                instrument_id=inst.id,
                bracket=2,
                initial_leverage=20,
                notional_floor=Decimal("50000"),
                notional_cap=Decimal("250000"),
                maint_margin_ratio=Decimal("0.025"),
                cum=Decimal("500"),
            ),
        ],
    )

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0")})
    mock_binance.set_leverage = AsyncMock(return_value={"leverage": 18})
    mock_binance.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_entry_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_stop_loss_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_sl_{kwargs.get('client_order_id', '1')}"})
    mock_binance.create_take_profit_order = AsyncMock(side_effect=lambda **kwargs: {"id": f"bin_tp_{kwargs.get('client_order_id', '1')}"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bracket_repo=bracket_repo,
        binance_client=mock_binance,
    )

    # Signal asks for 75x leverage with SL 5% away (Entry 60000, SL 57000)
    # SL distance = 5%, MMR = 1% -> Total buffer = 6% -> Max Safe Leverage = 1 / 0.06 = 16x
    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 60000 SL: 57000 TP: 63000",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60000"),
        entry_targets=[Decimal("60000")],
        sl_price=Decimal("57000"),
        tp_targets=[Decimal("63000")],
        leverage=75,
    )

    res = await trade_service.execute_signal(signal, account_id=acc.id)

    assert res.is_success is True
    assert res.symbol == "BTCUSDT"

    # Check trade recorded in DB with effective downscaled leverage (16x, NOT 75x)
    trade_repo = TradeRepository(async_session)
    saved_trade = await trade_repo.get(res.trade_id)
    assert saved_trade is not None
    assert saved_trade.leverage == 16

    # Verify Binance set_leverage was called with 16
    mock_binance.set_leverage.assert_called_with("BTCUSDT", 16)

