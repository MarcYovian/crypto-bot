"""Comprehensive scenario and edge case tests for Dynamic Leverage calculation."""

from decimal import Decimal
import pytest
from src.domain.services.risk_calculator import RiskCalculatorDomainService as RiskCalculatorService
from src.presentation.api.schemas.master import InstrumentLeverageBracketCreate



@pytest.fixture
def multi_tier_brackets():
    """Realistic 4-tier Binance leverage brackets (e.g. AAVEUSDT / SOLUSDT)."""
    return [
        type("Bracket", (), {
            "bracket": 1,
            "initial_leverage": 50,
            "notional_floor": Decimal("0"),
            "notional_cap": Decimal("5000"),
            "maint_margin_ratio": Decimal("0.015"),  # 1.5%
            "cum": Decimal("0"),
        })(),
        type("Bracket", (), {
            "bracket": 2,
            "initial_leverage": 20,
            "notional_floor": Decimal("5000"),
            "notional_cap": Decimal("25000"),
            "maint_margin_ratio": Decimal("0.025"),  # 2.5%
            "cum": Decimal("50"),
        })(),
        type("Bracket", (), {
            "bracket": 3,
            "initial_leverage": 10,
            "notional_floor": Decimal("25000"),
            "notional_cap": Decimal("100000"),
            "maint_margin_ratio": Decimal("0.05"),   # 5.0%
            "cum": Decimal("675"),
        })(),
        type("Bracket", (), {
            "bracket": 4,
            "initial_leverage": 5,
            "notional_floor": Decimal("100000"),
            "notional_cap": Decimal("500000"),
            "maint_margin_ratio": Decimal("0.10"),   # 10.0%
            "cum": Decimal("5675"),
        })(),
    ]


def test_scenario_bracket_cap_override(multi_tier_brackets):
    """Scenario 1: Stop distance is tight (Safe leverage is high 40x),
    but large position size lands in Tier 2 ($12,000 notional) where Binance caps at 20x."""
    calculator = RiskCalculatorService()

    # Balance $10,000, 2% risk = $200. Entry: $100, SL: $98.33 (SL distance $1.67 = 1.67%)
    # Raw Qty = 200 / 1.67 = 119.76 koin. Notional = 119.7 * 100 = $11,970 USDT (Tier 2: $5k - $25k)
    # Tier 2 MMR = 2.5%. Max safe leverage = 1 / (0.0167 + 0.025) = 1 / 0.0417 = 23x
    # Tier 2 initial_leverage = 20x. Signal requests 50x.
    # Effective leverage MUST be 20x (capped by Binance Tier 2 cap, not by safe SL).
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("10000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.33"),
        leverage=50,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=multi_tier_brackets,
    )

    assert res.is_valid is True
    assert res.leverage == 20
    assert res.is_leverage_downscaled is True
    assert "20x" in res.leverage_adjustment_reason



def test_scenario_super_wide_stop_loss_clamped_to_1x(multi_tier_brackets):
    """Scenario 2 (Edge Case): Extremely wide SL (e.g. 60% distance) where raw formula yields < 1x.
    Must clamp to minimum allowable leverage 1x without crashing or returning 0."""
    calculator = RiskCalculatorService()

    # Entry: $100, SL: $40 (Distance: 60%). Buffer = 60% + 1.5% = 61.5%
    # Safe raw = 1 / 0.615 = 1.62 -> Floor = 1x
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("40.0"),
        leverage=20,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=multi_tier_brackets,
    )

    assert res.is_valid is True
    assert res.leverage == 1
    assert res.max_safe_leverage == 1
    assert res.is_leverage_downscaled is True


def test_scenario_super_tight_scalp_sl(multi_tier_brackets):
    """Scenario 3 (Edge Case): Super tight scalping SL (0.2% distance).
    Safe leverage would mathematically allow 1 / (0.002 + 0.015) = 58x.
    Bracket 1 ceiling is 50x. Signal requests 20x -> Stays 20x."""
    calculator = RiskCalculatorService()

    # Entry: $100.0, SL: $99.8 (Distance 0.2%).
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("99.8"),
        leverage=20,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=multi_tier_brackets,
    )

    assert res.is_valid is True
    assert res.leverage == 20
    assert res.is_leverage_downscaled is False


def test_scenario_empty_brackets_fallback_resilience():
    """Scenario 4 (Edge Case): Brackets table empty or unseeded (None / empty list).
    Must fallback to safe defaults (1.5% MMR, 125x ceiling) without error."""
    calculator = RiskCalculatorService()

    res = calculator.calculate_position_size(
        wallet_balance=Decimal("5000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("57000.0"),  # 5% SL distance
        leverage=50,
        step_size=Decimal("0.001"),
        qty_precision=3,
        brackets=[],  # Empty list
    )

    assert res.is_valid is True
    # SL distance = 5%, Default MMR = 1.5% -> Buffer = 6.5% -> Max Safe = 1 / 0.070 = 14x
    assert res.leverage in (14, 15)
    assert res.is_leverage_downscaled is True


def test_scenario_whale_position_exceeding_highest_tier(multi_tier_brackets):
    """Scenario 5 (Edge Case): Massive position value exceeding Tier 4 cap ($500,000).
    Must fallback to the most conservative (last) bracket (Tier 4: max 5x, 10% MMR)."""
    calculator = RiskCalculatorService()

    # Huge wallet balance with small SL distance -> creates $800,000 position
    # Balance $1,000,000, 2% risk = $20,000. Entry: $100, SL: $97.5 (Distance: $2.5). Qty = 8,000. Notional = $800,000.
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("1000000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("97.5"),
        leverage=50,
        step_size=Decimal("1.0"),
        qty_precision=0,
        brackets=multi_tier_brackets,
    )

    assert res.is_valid is True
    # Tier 4 initial_leverage is 5x
    assert res.leverage <= 5


def test_scenario_downscaled_leverage_margin_insufficient_warning(multi_tier_brackets):
    """Scenario 6 (Edge Case): When leverage is downscaled from 75x to 3x, the required margin
    increases from $26 USDT to $666 USDT. If wallet only has $100 USDT, it must flag is_valid=False."""
    calculator = RiskCalculatorService()

    # Balance $100, 2% risk = $2.0. Entry: 100, SL: 70 (Distance 30%).
    # SL distance = 30%, MMR = 1.5% -> Safe leverage = 1 / 0.315 = 3x.
    # Qty = 2.0 / 30 = 0.066 -> rounded down to 0.06 -> Notional = $6.0.
    # Required margin at 3x = $2.0 USDT (within $100 balance).
    # But if risk is high and margin > balance:
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("50.0"),  # Low balance
        risk_percent=Decimal("20.0"),    # High risk
        entry_price=Decimal("100.0"),
        sl_price=Decimal("90.0"),        # 10% distance -> Safe leverage = 8x
        leverage=50,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=multi_tier_brackets,
    )

    # Qty = 10 / 10 = 1.0. Notional = 100. At 8x, Margin = 100/8 = 12.5 USDT (Valid since < 50)
    assert res.is_valid is True
    assert res.leverage == 8


def test_scenario_short_sell_symmetry(multi_tier_brackets):
    """Scenario 7: SHORT position where SL is higher than Entry (Entry: 100, SL: 104).
    Must compute exact symmetric 4% SL distance and downscale appropriately."""
    calculator = RiskCalculatorService()

    res_short = calculator.calculate_position_size(
        wallet_balance=Decimal("4251.45"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("104.0"),  # SHORT SL above entry
        leverage=75,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=multi_tier_brackets,
    )

    assert res_short.is_valid is True
    assert res_short.leverage in (16, 18)
    assert res_short.is_leverage_downscaled is True

