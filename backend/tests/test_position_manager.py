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

    await pm.close_trade(sample_trade, close_reason="TP3", exit_price=65000.0)

    # Verifikasi status CLOSED & pembatalan sisa order di Binance
    assert mock_trade_repo.update_trade_status.called
    assert mock_trade_repo.update_trade_status.call_args[0][0] == 1
    assert mock_trade_repo.update_trade_status.call_args[0][1] == "CLOSED"
    mock_execution_engine.exchange.cancel_all_orders.assert_called_with("BTCUSDT")

    # Verifikasi summary tersimpan
    mock_trade_repo.save_summary.assert_called_once()
    summary_kwargs = mock_trade_repo.save_summary.call_args[1]
    assert summary_kwargs['win'] == 1
    assert summary_kwargs['close_reason'] == "TP3"


@pytest.mark.asyncio
async def test_handle_order_fill_tp2_moves_sl_to_tp1(mock_trade_repo, mock_execution_engine, sample_trade):
    """Test bahwa ketika TP2 hit, Stop Loss otomatis digeser ke harga TP1 (Trailing Stop)."""
    sample_trade.tp1_price = 62000.0
    pm = PositionManager(mock_trade_repo, mock_execution_engine)

    tp2_order = Order(id=11, trade_id=1, purpose="TP2", side="SELL", qty=0.005)

    await pm.handle_order_fill(sample_trade, tp2_order, fill_price=64000.0, fill_qty=0.005)

    # Verifikasi status trade diupdate ke PARTIAL
    mock_trade_repo.update_trade_status.assert_called_with(1, "PARTIAL")

    # Verifikasi SL digeser ke harga TP1 ($62,000)
    mock_execution_engine.exchange.create_order.assert_called_once()
    call_args = mock_execution_engine.exchange.create_order.call_args[1]
    assert call_args['params']['stopPrice'] == 62000.0
    mock_trade_repo.log_event.assert_called_with(1, "SL_MOVED_TO_TP1", '{"tp1_price": 62000.0}')
