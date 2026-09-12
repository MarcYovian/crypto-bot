"""Unit and integration tests for BinanceExchangeAdapter WebSocket stream service."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Strategy, Trade, Order
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.gateways.binance import BinanceConnector, BinanceExchangeAdapter


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
async def test_websocket_adapter_init_modes():
    """Test BinanceExchangeAdapter and BinanceConnector initialization modes."""
    conn_demo = BinanceConnector(api_key="demo_key", secret_key="demo_sec", testnet=True)
    adapter_demo = BinanceExchangeAdapter(connector=conn_demo)
    assert adapter_demo.connector.testnet is True

    conn_live = BinanceConnector(api_key="live_key", secret_key="live_sec", testnet=False)
    adapter_live = BinanceExchangeAdapter(connector=conn_live)
    assert adapter_live.connector.testnet is False

    await adapter_demo.close()
    await adapter_live.close()


@pytest.mark.asyncio
async def test_websocket_adapter_start_order_stream_task():
    """Test start_order_stream_task returns None when unconfigured, and creates task when configured."""
    conn_no_key = BinanceConnector()
    adapter_no_key = BinanceExchangeAdapter(connector=conn_no_key)
    task_none = adapter_no_key.start_order_stream_task(on_fill_coro=AsyncMock())
    assert task_none is None

    conn_with_key = BinanceConnector(api_key="valid_key", secret_key="valid_sec")
    adapter_with_key = BinanceExchangeAdapter(connector=conn_with_key)
    with patch.object(adapter_with_key, "watch_orders_stream", new_callable=AsyncMock) as mock_watch:
        task = adapter_with_key.start_order_stream_task(on_fill_coro=AsyncMock())
        assert task is not None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_websocket_adapter_process_ws_order_event(async_session: AsyncSession, ws_env: dict):
    """Test processing raw WebSocket event through HandleOrderFillUseCase."""
    conn = BinanceConnector(api_key="key", secret_key="sec")
    adapter = BinanceExchangeAdapter(connector=conn)

    mock_fill_uc = AsyncMock(spec=HandleOrderFillUseCase)
    mock_fill_uc.execute_from_raw_event = AsyncMock(return_value={"status": "FILLED"})

    raw_event = {
        "id": "BIN_WS_12345",
        "symbol": "BTC/USDT:USDT",
        "status": "closed",
        "filled": 0.01,
        "average": 50000.0,
        "fee": {"cost": 0.02, "currency": "USDT"},
    }

    result = await adapter.process_ws_order_event(raw_event, handle_fill_use_case=mock_fill_uc)
    assert result == {"status": "FILLED"}
    mock_fill_uc.execute_from_raw_event.assert_awaited_once_with(raw_event)


@pytest.mark.asyncio
async def test_websocket_stream_reconnect_on_error():
    """Test that watch_orders_stream reconnects upon transient WebSocket errors."""
    conn = BinanceConnector(api_key="key", secret_key="sec")
    adapter = BinanceExchangeAdapter(connector=conn)

    mock_ws = AsyncMock()
    call_count = 0

    async def mock_watch_orders():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionResetError("1002 reserved bits frame reset")
        elif call_count == 2:
            return [{"id": "ORDER_1", "status": "closed"}]
        else:
            raise asyncio.CancelledError()

    mock_ws.watch_orders = mock_watch_orders
    conn.get_ws_exchange = AsyncMock(return_value=mock_ws)

    received_orders = []
    async def on_fill(order):
        received_orders.append(order)

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        try:
            await adapter.watch_orders_stream(callback_coro=on_fill)
        except asyncio.CancelledError:
            pass

    assert len(received_orders) == 1
    assert received_orders[0]["id"] == "ORDER_1"
    assert call_count >= 2
    mock_sleep.assert_called()
