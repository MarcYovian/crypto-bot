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
    engine.exchange = MagicMock()
    
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
        leverage=20,
        symbol_info=MagicMock(tick_size=0.1, step_size=0.001, min_qty=0.001, min_notional=5.0, price_precision=2, qty_precision=3, max_qty=9999.0)
    )

    assert res.success is True
    assert res.execution_type == "LIMIT"
    assert res.entry_order_id == "BINANCE_LIMIT_123"
    assert res.sl_order_id is None  # Order Limit menunda SL hingga FILLED
    mock_trade_repo.update_trade_status.assert_called_with(1, "WAITING_ENTRY")


@pytest.mark.asyncio
async def test_execute_trade_pipeline_market_order_recalculate_risk(mock_trade_repo, risk_res):
    """Test bahwa MARKET order menghitung ulang position_size menggunakan current_price terkini

    agar potensi risiko jika Stop Loss tersentuh tetap aman (misal pada ZEC/HBAR slippage).
    """
    engine = BinanceExecutionEngine(mock_trade_repo)
    engine.exchange = MagicMock()

    # Harga market saat ini bergeser ke $60,100 (bergeser naik dari target $60,000)
    # Masih di dalam toleransi 0.2% (60000 + 120 = 60120), sehingga diproses sebagai MARKET order.
    current_price = 60100.0
    engine.exchange.fetch_ticker = AsyncMock(return_value={'last': current_price})
    engine.exchange.set_margin_mode = AsyncMock()
    engine.exchange.set_leverage = AsyncMock()
    engine.exchange.cancel_all_orders = AsyncMock()
    engine.exchange.fetch_positions = AsyncMock(return_value=[{
        'entryPrice': current_price,
        'initialMargin': 60.0
    }])
    engine.exchange.create_order = AsyncMock(side_effect=[
        {'id': 'BINANCE_MARKET_ENTRY_123'},  # Entry order
        {'id': 'BINANCE_SL_456'},            # SL order
        {'id': 'BINANCE_TP_789'}             # TP1 order
    ])
    engine._wait_position_active = AsyncMock()

    mock_sym_info = MagicMock(
        symbol="BTCUSDT",
        price_precision=2,
        qty_precision=3,
        tick_size=0.1,
        step_size=0.001,
        min_qty=0.001,
        min_notional=5.0,
        max_qty=9999.0
    )

    # Initial risk_res position_size awal: 0.02 BTC (dihitung di target $60,000 dengan SL $59,000 -> distance $1000 -> $20 loss)
    # Ketika harga market naik ke $60,100, distance ke SL $59,000 menjadi $1,100.
    # Recalculated size: $20 / $1100 = 0.018 BTC (dibulatkan sesuai step_size 0.001).
    res: ExecutionResponse = await engine.execute_trade_pipeline(
        trade_id=1,
        symbol="BTCUSDT",
        side="BUY",
        risk_res=risk_res,
        tp_prices=[62000.0],
        leverage=20,
        symbol_info=mock_sym_info
    )

    assert res.success is True
    assert res.execution_type == "MARKET"
    assert res.entry_order_id == "BINANCE_MARKET_ENTRY_123"
    assert res.sl_order_id == "BINANCE_SL_456"

    # Verifikasi bahwa order entry yang dikirim ke Binance menggunakan size hasil hitung ulang (0.018 BTC, bukan 0.02 BTC)
    create_order_calls = engine.exchange.create_order.call_args_list
    entry_call_kwargs = create_order_calls[0].kwargs
    assert entry_call_kwargs['amount'] == 0.018
    assert entry_call_kwargs['amount'] < risk_res.position_size  # Terbukti otomatis mengecil agar risk aman $20!
