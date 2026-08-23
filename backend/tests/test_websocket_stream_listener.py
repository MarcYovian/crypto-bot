"""Unit and integration tests for BinanceStreamListener WebSocket service."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Strategy, Trade, Order
from src.domain.entities.trade import OrderFillDTO
from src.repository.trade_repository import TradeRepository
from src.services.position_manager import PositionManager
from src.services.websocket_listener import BinanceStreamListener

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create in-memory SQLite database session."""
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
async def ws_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(exchange_id=exchange.id, name="Test WS Acc", account_type="FUTURES", environment="TESTNET", is_active=True)
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
        status="OPEN", entry_price=Decimal("50000"), avg_entry_price=Decimal("50000"),
        sl_price=Decimal("48000"), leverage=10, position_size=Decimal("0.01"), remaining_qty=Decimal("0.01")
    )
    async_session.add(trade)
    await async_session.flush()

    order = Order(
        trade_id=trade.id, exchange_order_id="BIN_WS_12345", client_order_id="CLI_ENTRY_1",
        order_type="MARKET", purpose="ENTRY", side="BUY", price=Decimal("50000"), qty=Decimal("0.01"),
        status="NEW"
    )
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(trade)
    await async_session.refresh(order)

    return {"trade": trade, "order": order, "inst": inst}


@pytest.mark.asyncio
async def test_websocket_listener_init_modes(async_session: AsyncSession):
    """Test BinanceStreamListener testnet (demo) vs live initialization."""
    trade_repo = TradeRepository(async_session)
    mock_pos_mgr = MagicMock(spec=PositionManager)

    listener_demo = BinanceStreamListener(trade_repo=trade_repo, position_manager=mock_pos_mgr, testnet=True)
    assert listener_demo.is_running is False
    assert listener_demo.exchange is not None

    listener_live = BinanceStreamListener(trade_repo=trade_repo, position_manager=mock_pos_mgr, testnet=False)
    assert listener_live.is_running is False
    await listener_demo.stop()
    await listener_live.stop()


@pytest.mark.asyncio
async def test_websocket_listener_order_fill_event_dispatch(async_session: AsyncSession, ws_env: dict):
    """Test parsing a raw CCXT order event and dispatching OrderFillDTO to PositionManager."""
    env = ws_env
    trade_repo = TradeRepository(async_session)
    mock_pos_mgr = AsyncMock(spec=PositionManager)
    mock_pos_mgr.handle_order_fill = AsyncMock()

    listener = BinanceStreamListener(trade_repo=trade_repo, position_manager=mock_pos_mgr, testnet=True)

    raw_event = {
        "id": "BIN_WS_12345",
        "symbol": "BTC/USDT:USDT",
        "status": "closed",
        "filled": 0.01,
        "average": 50000.0,
        "fee": {"cost": 0.02, "currency": "USDT"},
    }

    await listener._process_ws_order_event(raw_event)

    mock_pos_mgr.handle_order_fill.assert_called_once()
    fill_dto: OrderFillDTO = mock_pos_mgr.handle_order_fill.call_args[0][0]
    assert fill_dto.order_id == env["order"].id
    assert fill_dto.trade_id == env["trade"].id
    assert fill_dto.symbol == "BTCUSDT"
    assert fill_dto.fill_price == Decimal("50000")
    assert fill_dto.fill_qty == Decimal("0.01")
    assert fill_dto.fee == Decimal("0.02")
    assert fill_dto.status == "FILLED"

    await listener.stop()


@pytest.mark.asyncio
async def test_websocket_listener_ignore_untracked_order(async_session: AsyncSession):
    """Test that events for order IDs not present in DB are safely skipped without errors."""
    trade_repo = TradeRepository(async_session)
    mock_pos_mgr = AsyncMock(spec=PositionManager)

    listener = BinanceStreamListener(trade_repo=trade_repo, position_manager=mock_pos_mgr, testnet=True)

    untracked_event = {
        "id": "UNKNOWN_EXCHANGE_ID_9999",
        "symbol": "ETH/USDT:USDT",
        "status": "closed",
        "filled": 1.0,
        "average": 3000.0,
    }

    await listener._process_ws_order_event(untracked_event)
    mock_pos_mgr.handle_order_fill.assert_not_called()
    await listener.stop()


@pytest.mark.asyncio
async def test_websocket_listener_start_loop_and_reconnect(async_session: AsyncSession):
    """Test start loop consumes orders and reconnects on exception."""
    trade_repo = TradeRepository(async_session)
    mock_pos_mgr = AsyncMock(spec=PositionManager)

    listener = BinanceStreamListener(trade_repo=trade_repo, position_manager=mock_pos_mgr, testnet=True)

    call_count = 0
    async def mock_watch_orders():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionResetError("WebSocket connection lost")
        elif call_count == 2:
            return [{"id": "NONE_ORDER", "status": "open"}]
        else:
            listener.is_running = False
            return []

    listener.exchange.watch_orders = mock_watch_orders

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        await listener.start()
        assert call_count >= 2
        mock_sleep.assert_called()

    await listener.stop()
