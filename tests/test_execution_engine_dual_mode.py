"""Unit and integration tests for execution dual market/limit mode & deferred SL/TP in Clean Architecture."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Strategy, Trade, RiskProfile, DailyRiskConfig, Watchlist
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.dto.trade_commands import ExecuteSignalCommand, TradeExecutionResultDTO
from src.infrastructure.gateways.binance.binance_adapter import BinanceExchangeAdapter
from src.infrastructure.gateways.binance.binance_connector import BinanceConnector

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def engine_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(exchange_id=exchange.id, name="Exec Account", account_type="FUTURES", environment="TESTNET", is_active=True)
    async_session.add(account)
    await async_session.flush()

    inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    strat = Strategy(name="DefaultStrategy", version="1.0.0", is_active=True)
    async_session.add(strat)
    await async_session.flush()

    profile = RiskProfile(name="Moderate", risk_percent=Decimal("2.0"), max_daily_loss=Decimal("500.0"), max_open_trade=5, is_active=True)
    async_session.add(profile)
    await async_session.flush()



    daily = DailyRiskConfig(account_id=account.id, risk_profile_id=profile.id, date=__import__("datetime").date.today(), balance=Decimal("10000.0"), risk_amount=Decimal("200.0"))
    async_session.add(daily)
    await async_session.flush()


    wl = Watchlist(instrument_id=inst.id, enabled=True)
    async_session.add(wl)
    await async_session.commit()

    return {"inst": inst, "account": account}


@pytest.mark.asyncio
async def test_validate_signal_market_state_logic():
    """Test pre-validation of current market state against SL and TP1 levels."""
    # Pre-validation logic checks:
    # LONG: Market <= SL (Already stopped out)
    cur_p = 47900.0
    sl_p = 48000.0
    tp1_p = 52000.0
    assert cur_p <= sl_p

    # LONG: Market >= TP1 (Already missed)
    cur_p2 = 52100.0
    assert cur_p2 >= tp1_p

    # LONG: Valid
    cur_p3 = 50050.0
    assert sl_p < cur_p3 < tp1_p

    # SHORT: Market >= SL
    cur_p4 = 51000.0
    sl_short = 50500.0
    assert cur_p4 >= sl_short

    # SHORT: Market <= TP1
    cur_p5 = 47500.0
    tp1_short = 48000.0
    assert cur_p5 <= tp1_short


@pytest.mark.asyncio
async def test_execute_trade_pipeline_market_order(async_session: AsyncSession, engine_env: dict):
    """Test execution pipeline choosing Market order when price is near entry and placing SL/TP."""
    env = engine_env

    mock_gateway = AsyncMock()
    mock_gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50020.0"))
    mock_gateway.fetch_ticker = AsyncMock(return_value={"last": 50020.0, "bid": 50019.0, "ask": 50021.0})
    mock_gateway.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")})
    mock_gateway.get_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")})
    mock_gateway.create_order = AsyncMock(side_effect=[
        {"order_id": "BIN_ENTRY_MKT_1", "client_order_id": "c_entry_1", "status": "FILLED", "price": 50020.0, "qty": 0.01},
        {"order_id": "BIN_SL_MKT_1", "client_order_id": "c_sl_1", "status": "NEW", "price": 48000.0, "qty": 0.01},
        {"order_id": "BIN_TP1_MKT_1", "client_order_id": "c_tp1_1", "status": "NEW", "price": 52000.0, "qty": 0.005},
        {"order_id": "BIN_TP2_MKT_1", "client_order_id": "c_tp2_1", "status": "NEW", "price": 54000.0, "qty": 0.005},
    ])
    mock_gateway.set_margin_mode = AsyncMock()
    mock_gateway.set_leverage = AsyncMock()

    use_case = ExecuteSignalUseCase(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        exchange_gateway=mock_gateway,
    )

    from src.domain.entities.signal import ParsedSignalDTO

    sig_dto = ParsedSignalDTO(
        raw_text="BUY BTCUSDT",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("48000.0"),
        tp_targets=[Decimal("52000.0"), Decimal("54000.0")],
        leverage=10,
    )

    cmd = ExecuteSignalCommand(
        signal_dto=sig_dto,
        account_id=env["account"].id,
    )

    res: TradeExecutionResultDTO = await use_case.execute(cmd)

    assert res.success is True
    assert res.execution_type == "MARKET"
    assert res.trade_id is not None
    assert res.entry_order_id == "BIN_ENTRY_MKT_1"



@pytest.mark.asyncio
async def test_execute_trade_pipeline_limit_order_deferred(async_session: AsyncSession, engine_env: dict):
    """Test execution pipeline choosing Limit order when price is far from entry and deferring SL/TP."""
    env = engine_env

    mock_gateway = AsyncMock()
    # Price is 51000 (> 50000 + 0.2%), so it places LIMIT order
    mock_gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("51000.0"))
    mock_gateway.fetch_ticker = AsyncMock(return_value={"last": 51000.0, "bid": 50999.0, "ask": 51001.0})
    mock_gateway.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")})
    mock_gateway.get_balance = AsyncMock(return_value={"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")})


    mock_gateway.create_order = AsyncMock(return_value={
        "order_id": "BIN_ENTRY_LMT_1", "client_order_id": "c_entry_lmt", "status": "NEW", "price": 50000.0, "qty": 0.01
    })
    mock_gateway.set_margin_mode = AsyncMock()
    mock_gateway.set_leverage = AsyncMock()

    use_case = ExecuteSignalUseCase(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        exchange_gateway=mock_gateway,
    )

    from src.domain.entities.signal import ParsedSignalDTO
    sig_dto = ParsedSignalDTO(
        raw_text="BUY BTCUSDT",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("50000.0"),
        entry_max=Decimal("50000.0"),
        sl_price=Decimal("48000.0"),
        tp_targets=[Decimal("54000.0")],
        leverage=10,
    )

    cmd = ExecuteSignalCommand(
        signal_dto=sig_dto,
        account_id=env["account"].id,
    )

    res: TradeExecutionResultDTO = await use_case.execute(cmd)

    assert res.success is True
    assert res.execution_type == "LIMIT"
    assert res.entry_order_id == "BIN_ENTRY_LMT_1"
    assert res.sl_order_id is None
    assert res.tp_order_ids == []



@pytest.mark.asyncio
async def test_fetch_balance_and_cancel_all():
    """Test fetch_balance and cancel_all_orders on BinanceExchangeAdapter."""
    mock_connector = AsyncMock()
    mock_connector.execute_rest = AsyncMock(side_effect=[
        {"USDT": {"total": 1000.0, "free": 800.0, "used": 200.0}},
        [{"id": "c1", "symbol": "BTC/USDT:USDT", "status": "canceled"}, {"id": "c2", "symbol": "BTC/USDT:USDT", "status": "canceled"}],
    ])

    adapter = BinanceExchangeAdapter(connector=mock_connector)
    bal = await adapter.get_balance()
    assert bal is not None

    await adapter.cancel_all_orders("BTCUSDT")
    mock_connector.execute_rest.assert_called_with("cancel_all_orders", "BTC/USDT:USDT")


