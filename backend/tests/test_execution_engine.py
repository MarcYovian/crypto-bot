import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.execution_engine import BinanceExecutionEngine, ExecutionResponse
from src.services.risk_calculator import RiskCalculationResult
from src.repository.trade_repository import TradeRepository


@pytest.fixture
def mock_trade_repo():
    repo = MagicMock(spec=TradeRepository)
    repo.create_order = AsyncMock()
    repo.update_trade_status = AsyncMock()
    repo.log_event = AsyncMock()
    return repo


@pytest.fixture
def risk_res():
    return RiskCalculationResult(
        is_valid=True,
        risk_amount=20.0,
        entry_price=60000.0,
        stop_loss_price=59000.0,
        stop_distance=1000.0,
        stop_distance_percent=1.66,
        position_size=0.02,
        notional_value=1200.0,
        required_margin=60.0,
        leverage=20
    )


@pytest.mark.asyncio
async def test_validate_signal_market_state_tp1_reached(mock_trade_repo):
    engine = BinanceExecutionEngine(mock_trade_repo)

    # Harga market $62,500 sudah tembus TP1 ($62,000) untuk sinyal BUY
    is_valid, msg = await engine.validate_signal_market_state(
        current_price=62500.0,
        entry_price=60000.0,
        sl_price=59000.0,
        tp1_price=62000.0,
        side="BUY"
    )

    assert is_valid is False
    assert "EXPIRED" in msg


@pytest.mark.asyncio
async def test_validate_signal_market_state_sl_breached(mock_trade_repo):
    engine = BinanceExecutionEngine(mock_trade_repo)

    # Harga market $58,500 sudah di bawah SL ($59,000) untuk sinyal BUY
    is_valid, msg = await engine.validate_signal_market_state(
        current_price=58500.0,
        entry_price=60000.0,
        sl_price=59000.0,
        tp1_price=62000.0,
        side="BUY"
    )

    assert is_valid is False
    assert "REJECTED" in msg


@pytest.mark.asyncio
async def test_execute_trade_pipeline_limit_order(mock_trade_repo, risk_res):
    engine = BinanceExecutionEngine(mock_trade_repo)
    
    # Mock CCXT Pro Exchange Methods
    engine.exchange.fetch_ticker = AsyncMock(return_value={'last': 60500.0})  # Harga di atas harga entry + toleransi (Limit)
    engine.exchange.set_margin_mode = AsyncMock()
    engine.exchange.set_leverage = AsyncMock()
    engine.exchange.create_order = AsyncMock(return_value={'id': 'BINANCE_LIMIT_123'})

    res: ExecutionResponse = await engine.execute_trade_pipeline(
        trade_id=1,
        symbol="BTCUSDT",
        side="BUY",
        risk_res=risk_res,
        tp_prices=[62000.0],
        leverage=20
    )

    assert res.success is True
    assert res.execution_type == "LIMIT"
    assert res.entry_order_id == "BINANCE_LIMIT_123"
    assert res.sl_order_id is None  # Order Limit menunda SL hingga FILLED
    mock_trade_repo.update_trade_status.assert_called_with(1, "WAITING_ENTRY")
