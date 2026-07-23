import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.position_manager import PositionManager
from src.database.models import Trade, Order


@pytest.fixture
def mock_trade_repo():
    repo = MagicMock()
    repo.update_trade_status = AsyncMock()
    repo.log_event = AsyncMock()
    repo.create_order = AsyncMock()
    repo.save_summary = AsyncMock()
    return repo


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock()
    engine.exchange = MagicMock()
    engine.exchange.create_order = AsyncMock(return_value={'id': 'BEP_SL_999'})
    engine.exchange.cancel_all_orders = AsyncMock()
    return engine


@pytest.fixture
def sample_trade():
    return Trade(
        id=1,
        symbol="BTCUSDT",
        side="BUY",
        status="OPEN",
        entry_price=60000.0,
        sl_price=59000.0,
        position_size=0.02,
        remaining_qty=0.02,
        leverage=20
    )


@pytest.mark.asyncio
async def test_handle_order_fill_tp1_moves_sl_to_bep(mock_trade_repo, mock_execution_engine, sample_trade):
    pm = PositionManager(mock_trade_repo, mock_execution_engine)

    tp1_order = Order(id=10, trade_id=1, purpose="TP1", side="SELL", qty=0.01)

    await pm.handle_order_fill(sample_trade, tp1_order, fill_price=62000.0, fill_qty=0.01)

    # Verifikasi status trade diupdate ke PARTIAL
    mock_trade_repo.update_trade_status.assert_called_with(1, "PARTIAL")

    # Verifikasi SL digeser ke BEP ($60,000)
    mock_execution_engine.exchange.create_order.assert_called_once()
    call_args = mock_execution_engine.exchange.create_order.call_args[1]
    assert call_args['params']['stopPrice'] == 60000.0


@pytest.mark.asyncio
async def test_close_trade_generates_summary(mock_trade_repo, mock_execution_engine, sample_trade):
    pm = PositionManager(mock_trade_repo, mock_execution_engine)

    sl_order = Order(id=11, trade_id=1, purpose="SL", side="SELL", qty=0.02)

    await pm.handle_order_fill(sample_trade, sl_order, fill_price=59000.0, fill_qty=0.02)

    # Verifikasi status CLOSED & remaining orders dicancel
    mock_trade_repo.update_trade_status.assert_called()
    mock_execution_engine.exchange.cancel_all_orders.assert_called_with("BTCUSDT")

    # Verifikasi Summary dibuat
    mock_trade_repo.save_summary.assert_called_once()
