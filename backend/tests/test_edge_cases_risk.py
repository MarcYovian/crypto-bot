"""Edge test cases for RiskCalculatorService and PrecisionFilterService."""

from decimal import Decimal
import pytest

from src.services.precision_filter import PrecisionFilterService, SymbolInfo
from src.services.risk_calculator import RiskCalculatorService
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    MaxRiskExceededError,
    InsufficientMarginRiskError,
)


@pytest.fixture
def risk_calc():
    return RiskCalculatorService()


# =============================================================================
# 1. MICRO STOP LOSS & MATHEMATICAL BOUNDARIES
# =============================================================================

def test_micro_stop_distance_sizing(risk_calc: RiskCalculatorService):
    """Test position sizing when stop distance is extremely narrow ($0.01)."""
    # Entry $50,000.00, SL $49,999.99 (Stop distance = 0.01)
    # Risk 2% on $1,000 = $20
    # Raw qty = 20 / 0.01 = 2000 BTC.
    # Anti-liquidation & MMR must clamp leverage so position doesn't liquidate prematurely.
def test_micro_stop_distance_sizing(risk_calc: RiskCalculatorService):
    """Test position sizing when stop distance is extremely narrow ($0.01)."""
    # Entry $50,000.00, SL $49,999.99 (Stop distance = 0.01)
    # Risk 2% on $1,000 = $20 -> Raw qty = 2000 BTC.
    # Required margin at 20x = $5,000,000 which exceeds $1,000 wallet balance.
    # The risk calculator must safely reject the order (is_valid = False) due to insufficient margin.
    res_extreme = risk_calc.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.00"),
        sl_price=Decimal("49999.99"),
        leverage=20,
        step_size=Decimal("0.001"),
        qty_precision=3,
        min_notional=Decimal("5.0"),
    )
    assert res_extreme.is_valid is False
    assert "Required margin" in (res_extreme.warning or "")

    # Valid narrow stop distance within wallet margin (e.g. SL $49,900 on $1,000 balance)
    res_valid = risk_calc.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.00"),
        sl_price=Decimal("49900.00"),
        leverage=20,
        step_size=Decimal("0.001"),
        qty_precision=3,
        min_notional=Decimal("5.0"),
    )
    assert res_valid.is_valid is True
    actual_sl_loss = res_valid.position_size * res_valid.stop_distance
    assert actual_sl_loss <= Decimal("20.0")


def test_zero_stop_distance_raises_error(risk_calc: RiskCalculatorService):
    """Test that entry_price == sl_price raises ZeroStopDistanceError."""
    with pytest.raises(ZeroStopDistanceError):
        risk_calc.calculate_position_size(
            wallet_balance=Decimal("1000.0"),
            risk_percent=Decimal("2.0"),
            entry_price=Decimal("50000.00"),
            sl_price=Decimal("50000.00"),
            leverage=10,
        )


def test_zero_or_negative_wallet_balance_handling(risk_calc: RiskCalculatorService):
    """Test that wallet_balance <= 0 returns is_valid=False with warning."""
    res_zero = risk_calc.calculate_position_size(
        wallet_balance=Decimal("0.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.00"),
        sl_price=Decimal("48000.00"),
        leverage=10,
    )
    assert res_zero.is_valid is False
    assert "must be positive" in (res_zero.warning or "")

    res_neg = risk_calc.calculate_position_size(
        wallet_balance=Decimal("-50.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.00"),
        sl_price=Decimal("48000.00"),
        leverage=10,
    )
    assert res_neg.is_valid is False
    assert "must be positive" in (res_neg.warning or "")


# =============================================================================
# 2. MIN NOTIONAL & LOT SIZING CONSTRAINTS
# =============================================================================

def test_sub_min_notional_rejection(risk_calc: RiskCalculatorService):
    """Test that tiny accounts where order notional < $5.0 are marked invalid."""
    # Wallet $10, Risk 2% = $0.20
    # Entry $50,000, SL $45,000 (Stop distance $5,000)
    # Raw Qty = 0.20 / 5000 = 0.00004 BTC -> Floored to 0.000
    # Notional = 0.000 * 50000 = $0.0 (below Binance min_notional $5.0)
    res = risk_calc.calculate_position_size(
        wallet_balance=Decimal("10.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("45000.0"),
        leverage=10,
        min_notional=Decimal("5.0"),
    )

    assert res.is_valid is False
    assert "below minimum required" in (res.warning or "")


def test_precision_step_size_round_floor():
    """Verify that PrecisionFilterService.round_quantity always floors down."""
    # When raw qty is 0.01599 and step size is 0.001, floor rounding gives 0.015 (NOT 0.016)
    rounded = PrecisionFilterService.round_quantity(
        qty=Decimal("0.01599"),
        step_size=Decimal("0.001"),
        qty_precision=3,
        round_down=True,
    )
    assert rounded == Decimal("0.015")

    # When raw qty is exactly step size multiple
    rounded_exact = PrecisionFilterService.round_quantity(
        qty=Decimal("0.020"),
        step_size=Decimal("0.001"),
        qty_precision=3,
        round_down=True,
    )
    assert rounded_exact == Decimal("0.020")


def test_precision_price_tick_size_rounding():
    """Verify that PrecisionFilterService.round_price rounds to nearest tick size."""
    # Tick size 0.10
    assert PrecisionFilterService.round_price(Decimal("50000.14"), tick_size=Decimal("0.10"), price_precision=2) == Decimal("50000.10")
    assert PrecisionFilterService.round_price(Decimal("50000.16"), tick_size=Decimal("0.10"), price_precision=2) == Decimal("50000.20")


# =============================================================================
# 3. LEVERAGE CLAMPING & TIERED BRACKET SCENARIOS
# =============================================================================

def test_leverage_clamping_bounds():
    """Verify leverage clamp to exchange bounds (1x to 125x)."""
    assert PrecisionFilterService.clamp_leverage(0, max_leverage=125, min_leverage=1) == 1
    assert PrecisionFilterService.clamp_leverage(150, max_leverage=125, min_leverage=1) == 125
    assert PrecisionFilterService.clamp_leverage(25, max_leverage=20, min_leverage=1) == 20
    assert PrecisionFilterService.clamp_leverage(10, max_leverage=50, min_leverage=1) == 10
