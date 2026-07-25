import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.execution_engine import BinanceExecutionEngine
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult
from src.services.precision_filter import SymbolInfo, PrecisionFilterService
from src.database.models import Trade


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock(spec=BinanceExecutionEngine)
    engine.exchange = MagicMock()
    return engine


# TC-01: Sinyal Long masuk saat harga sudah menembus SL (harga_saat_ini <= SL) -> HARUS REJECT
@pytest.mark.asyncio
async def test_tc01_signal_long_below_sl_rejected(mock_execution_engine):
    engine = BinanceExecutionEngine(mock_execution_engine.exchange)
    
    # Current Price 58000, SL 59000, TP1 62000 (Harga sudah tembus SL ke bawah)
    is_valid, reason = await engine.validate_signal_market_state(
        side="BUY", current_price=58000.0, entry_price=60000.0, sl_price=59000.0, tp1_price=62000.0
    )
    
    assert is_valid is False
    assert "SL" in reason and "menembus" in reason


# TC-02: Sinyal Long masuk saat harga sudah melewati TP1 (harga_saat_ini >= TP1) -> HARUS REJECT
@pytest.mark.asyncio
async def test_tc02_signal_long_above_tp1_rejected(mock_execution_engine):
    engine = BinanceExecutionEngine(mock_execution_engine.exchange)
    
    # Current Price 63000, SL 59000, TP1 62000 (Harga sudah naik lewati TP1)
    is_valid, reason = await engine.validate_signal_market_state(
        side="BUY", current_price=63000.0, entry_price=60000.0, sl_price=59000.0, tp1_price=62000.0
    )
    
    assert is_valid is False
    assert "EXPIRED" in reason


# TC-03 & TC-04: Crash & WebSocket Offline Recovery Sync Check
@pytest.mark.asyncio
async def test_tc03_tc04_failsafe_sync_check_recovers_trade_status(mock_execution_engine):
    from src.services.scheduler_service import CronSchedulerService
    
    # Mock Binance fetch_positions wrapper V2 mengembalikan posisi aktif untuk BTCUSDT
    mock_execution_engine.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'BTCUSDT', 'contracts': 0.05, 'positionAmt': 0.05}
    ])
    
    scheduler = CronSchedulerService(mock_execution_engine)
    
    # Trade di DB masih WAITING_ENTRY
    waiting_trade = Trade(id=1, symbol="BTCUSDT", side="BUY", status="WAITING_ENTRY")
    
    with patch("src.repository.trade_repository.TradeRepository.get_active_trades", AsyncMock(return_value=[waiting_trade])), \
         patch("src.repository.trade_repository.TradeRepository.update_trade_status", AsyncMock()) as mock_update, \
         patch("src.repository.trade_repository.TradeRepository.log_event", AsyncMock()):
        
        await scheduler._job_failsafe_sync_check()
        
        # Verifikasi status trade di DB otomatis ter-recovery menjadi OPEN
        mock_update.assert_called_once_with(1, "OPEN")


# TC-05: Risk Guard jika Saldo Terlalu Kecil -> Dinamis dinaikkan ke min_notional / min_qty
def test_tc05_insufficient_balance_below_min_notional():
    symbol_info = SymbolInfo("BTCUSDT", price_precision=2, qty_precision=3, tick_size=0.10, step_size=0.001, min_qty=0.001, min_notional=5.0)
    
    # Daily Risk $0.10 (Sangat kecil)
    result: RiskCalculationResult = RiskCalculatorService.calculate_position(
        daily_risk_amount=0.10,
        entry_price=60000.0,
        stop_loss_price=59000.0,
        side="BUY",
        max_leverage=20,
        symbol_info=symbol_info
    )
    
    # Berhasil direkalkulasi ke min_qty / min_notional
    assert result.is_valid is True
    assert result.position_size >= symbol_info.min_qty


# TC-06: Precision Guard pada Koin Desimal Banyak (PEPEUSDT) -> Dibulatkan menggunakan step_size tanpa error
def test_tc06_high_decimal_precision_lot_rounding():
    # PEPEUSDT step_size 100.0 (Lot kelipatan 100)
    symbol_info = SymbolInfo("PEPEUSDT", price_precision=7, qty_precision=0, tick_size=0.0000001, step_size=100.0, min_qty=100.0, min_notional=5.0)
    
    # Raw Qty = 15482.891
    formatted_qty = PrecisionFilterService.format_qty(15482.891, symbol_info)
    
    # Harus terbulat ke bawah (floor) kelipatan 100 -> 15400.0
    assert formatted_qty == 15400.0
