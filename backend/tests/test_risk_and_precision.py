import pytest
from src.services.precision_filter import PrecisionFilterService, SymbolInfo
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult


@pytest.fixture
def btc_symbol_info():
    return SymbolInfo(
        symbol="BTCUSDT",
        price_precision=2,
        qty_precision=3,
        tick_size=0.10,
        step_size=0.001,
        min_qty=0.001,
        min_notional=5.0
    )


@pytest.fixture
def kaito_symbol_info():
    return SymbolInfo(
        symbol="KAITOUSDT",
        price_precision=4,
        qty_precision=0,
        tick_size=0.0001,
        step_size=1.0,
        min_qty=1.0,
        min_notional=5.0
    )


def test_precision_filter_formatting(btc_symbol_info):
    # Test harga
    formatted_price = PrecisionFilterService.format_price(64200.5482, btc_symbol_info)
    assert formatted_price == 64200.50

    # Test Qty Floor (harus dibulatkan ke bawah)
    formatted_qty = PrecisionFilterService.format_qty(0.1239, btc_symbol_info)
    assert formatted_qty == 0.123  # Tidak boleh 0.124 agar risk tidak membengkak


def test_risk_calculator_normal_buy(btc_symbol_info):
    # Risk $10 USDT, Entry $60,000, SL $59,000 (Stop Distance = $1,000)
    # Raw Qty = 10 / 1000 = 0.01 BTC
    result: RiskCalculationResult = RiskCalculatorService.calculate_position(
        daily_risk_amount=10.0,
        entry_price=60000.0,
        stop_loss_price=59000.0,
        side="BUY",
        max_leverage=10,
        symbol_info=btc_symbol_info
    )

    assert result.is_valid is True
    assert result.position_size == 0.01
    assert result.stop_distance == 1000.0
    assert result.notional_value == 600.0
    assert result.required_margin == 60.0  # 600 / 10 leverage
    assert result.error_message is None


def test_risk_calculator_min_notional_fail(btc_symbol_info):
    # Risk $0.1 USDT dengan SL yang sangat jauh -> Qty sangat kecil -> Direkalkulasi ke min_qty
    result: RiskCalculationResult = RiskCalculatorService.calculate_position(
        daily_risk_amount=0.1,
        entry_price=60000.0,
        stop_loss_price=50000.0,
        side="BUY",
        max_leverage=10,
        symbol_info=btc_symbol_info
    )

    assert result.is_valid is True
    assert result.position_size >= btc_symbol_info.min_qty


def test_risk_calculator_same_entry_sl(btc_symbol_info):
    result: RiskCalculationResult = RiskCalculatorService.calculate_position(
        daily_risk_amount=10.0,
        entry_price=60000.0,
        stop_loss_price=60000.0,
        side="BUY",
        max_leverage=10,
        symbol_info=btc_symbol_info
    )

    assert result.is_valid is False
    assert result.error_message == "Entry and Stop Loss prices cannot be identical."
