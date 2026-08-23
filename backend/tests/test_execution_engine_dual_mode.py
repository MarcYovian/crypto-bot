"""Unit and integration tests for BinanceExecutionEngine (dual market/limit mode & deferred SL/TP)."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Strategy, Trade
from src.repository.trade_repository import TradeRepository
from src.services.precision_filter import SymbolInfo
from src.services.risk_calculator import RiskCalculationResult
from src.services.execution_engine import BinanceExecutionEngine, ExecutionResponse

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

    trade = Trade(
        account_id=account.id, instrument_id=inst.id, strategy_id=strat.id, side="BUY",
        status="WAITING_ENTRY", entry_price=Decimal("50000"), avg_entry_price=Decimal("50000"),
        sl_price=Decimal("48000"), leverage=10, position_size=Decimal("0.01"), remaining_qty=Decimal("0.01")
    )
    async_session.add(trade)
    await async_session.commit()
    await async_session.refresh(trade)

    return {"trade": trade, "inst": inst}


@pytest.mark.asyncio
async def test_validate_signal_market_state():
    """Test pre-validation of current market state against SL and TP1 levels."""
    engine = BinanceExecutionEngine()

    # LONG: Market <= SL (Already stopped out)
    valid, msg = await engine.validate_signal_market_state(
        current_price=47900.0, entry_price=50000.0, sl_price=48000.0, tp1_price=52000.0, side="BUY"
    )
    assert valid is False
    assert "REJECTED" in msg

    # LONG: Market >= TP1 (Already missed/profited)
    valid, msg = await engine.validate_signal_market_state(
        current_price=52100.0, entry_price=50000.0, sl_price=48000.0, tp1_price=52000.0, side="BUY"
    )
    assert valid is False
    assert "EXPIRED" in msg

    # LONG: Valid
    valid, msg = await engine.validate_signal_market_state(
        current_price=50050.0, entry_price=50000.0, sl_price=48000.0, tp1_price=52000.0, side="BUY"
    )
    assert valid is True
    assert msg == "VALID"

    # SHORT: Market >= SL
    valid, msg = await engine.validate_signal_market_state(
        current_price=51000.0, entry_price=50000.0, sl_price=50500.0, tp1_price=48000.0, side="SELL"
    )
    assert valid is False
    assert "REJECTED" in msg

    # SHORT: Market <= TP1
    valid, msg = await engine.validate_signal_market_state(
        current_price=47500.0, entry_price=50000.0, sl_price=50500.0, tp1_price=48000.0, side="SELL"
    )
    assert valid is False
    assert "EXPIRED" in msg

    await engine.close_connection()


@pytest.mark.asyncio
async def test_execute_trade_pipeline_market_order(async_session: AsyncSession, engine_env: dict):
    """Test execution pipeline choosing Market order when price is near entry and placing SL/TP."""
    env = engine_env
    trade_repo = TradeRepository(async_session)

    engine = BinanceExecutionEngine(trade_repo=trade_repo)
    engine.exchange = AsyncMock()
    engine.exchange.fetch_ticker = AsyncMock(return_value={"last": 50020.0})
    engine.exchange.create_order = AsyncMock(side_effect=[
        {"id": "BIN_ENTRY_MKT_1"},  # Entry order
        {"id": "BIN_SL_MKT_1"},     # SL order
        {"id": "BIN_TP1_MKT_1"},    # TP1 order
        {"id": "BIN_TP2_MKT_1"},    # TP2 order
    ])
    engine.exchange.set_margin_mode = AsyncMock()
    engine.exchange.set_leverage = AsyncMock()
    engine.exchange.cancel_all_orders = AsyncMock()
    engine.exchange.fetch_positions = AsyncMock(return_value=[
        {"entryPrice": 50020.0, "initialMargin": 50.02, "contracts": 0.01}
    ])

    risk_res = RiskCalculationResult(
        is_valid=True,
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("48000.0"),
        stop_distance=Decimal("2000.0"),
        position_size=Decimal("0.01"),
        risk_amount=Decimal("20.0"),
        required_margin=Decimal("50.0"),
        risk_percent=Decimal("2.0"),
        leverage=10
    )

    symbol_info = SymbolInfo(
        symbol="BTCUSDT",
        price_precision=2,
        tick_size=0.10,
        step_size=0.001,
        min_qty=0.001,
        min_notional=5.0,
        max_qty=1000.0
    )

    with patch.object(engine, "_wait_position_active", AsyncMock()):
        resp: ExecutionResponse = await engine.execute_trade_pipeline(
            trade_id=env["trade"].id,
            symbol="BTCUSDT",
            side="BUY",
            risk_res=risk_res,
            tp_prices=[52000.0, 54000.0],
            leverage=10,
            symbol_info=symbol_info
        )

    assert resp.success is True
    assert resp.execution_type == "MARKET"
    assert resp.entry_order_id == "BIN_ENTRY_MKT_1"
    assert resp.sl_order_id == "BIN_SL_MKT_1"
    assert len(resp.tp_order_ids) == 2
    assert resp.actual_entry_price == 50020.0

    await engine.close_connection()


@pytest.mark.asyncio
async def test_execute_trade_pipeline_limit_order_deferred(async_session: AsyncSession, engine_env: dict):
    """Test execution pipeline choosing Limit order when price is far from entry and deferring SL/TP."""
    env = engine_env
    trade_repo = TradeRepository(async_session)

    engine = BinanceExecutionEngine(trade_repo=trade_repo)
    engine.exchange = AsyncMock()
    # Price is 51000 (> 50000 + 0.2%), so it places LIMIT order
    engine.exchange.fetch_ticker = AsyncMock(return_value={"last": 51000.0})
    engine.exchange.create_order = AsyncMock(return_value={"id": "BIN_ENTRY_LMT_1"})
    engine.exchange.set_margin_mode = AsyncMock()
    engine.exchange.set_leverage = AsyncMock()
    engine.exchange.fetch_positions = AsyncMock(return_value=[])

    risk_res = RiskCalculationResult(
        is_valid=True,
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("48000.0"),
        stop_distance=Decimal("2000.0"),
        position_size=Decimal("0.01"),
        risk_amount=Decimal("20.0"),
        required_margin=Decimal("50.0"),
        risk_percent=Decimal("2.0"),
        leverage=10
    )

    resp: ExecutionResponse = await engine.execute_trade_pipeline(
        trade_id=env["trade"].id,
        symbol="BTCUSDT",
        side="BUY",
        risk_res=risk_res,
        tp_prices=[54000.0],
        leverage=10,
    )

    assert resp.success is True
    assert resp.execution_type == "LIMIT"
    assert resp.entry_order_id == "BIN_ENTRY_LMT_1"
    assert resp.sl_order_id is None
    assert resp.tp_order_ids == []

    await engine.close_connection()


@pytest.mark.asyncio
async def test_fetch_balance_and_cancel_all():
    """Test fetch_balance and cancel_all_orders helper methods."""
    engine = BinanceExecutionEngine()
    engine.exchange = AsyncMock()
    engine.exchange.fetch_balance = AsyncMock(return_value={
        "USDT": {"total": 1000.0, "free": 800.0, "used": 200.0}
    })
    engine.exchange.cancel_all_orders = AsyncMock()

    bal = await engine.fetch_balance()
    assert bal["USDT"]["total"] == 1000.0
    assert bal["USDT"]["free"] == 800.0

    await engine.cancel_all_orders("BTCUSDT")
    engine.exchange.cancel_all_orders.assert_called_with("BTCUSDT")

    await engine.close_connection()
