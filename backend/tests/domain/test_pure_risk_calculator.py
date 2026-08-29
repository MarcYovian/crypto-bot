"""Unit tests for pure domain RiskCalculatorDomainService."""

from decimal import Decimal
import pytest

from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.services.precision_filter import PrecisionFilterDomainService
from src.domain.value_objects.side import OrderSide
from src.domain.exceptions.risk import ZeroStopDistanceError


def test_2_percent_risk_rule_sizing():
    # Balance 10,000 USDT, Risk 2.0% -> 200 USDT Risk Budget
    # Entry: 50,000, SL: 48,000 -> Stop Distance: 2,000 USDT
    # Expected Position Size: 200 / 2,000 = 0.1 BTC
    result = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("10000"),
        entry_price=Decimal("50000"),
        sl_price=Decimal("48000"),
        risk_percent=Decimal("2.0"),
        requested_leverage=10,
        step_size=Decimal("0.001"),
        tp_targets=[Decimal("52000"), Decimal("55000")],
    )

    assert result.is_valid is True
    assert result.risk_amount == Decimal("200.00")
    assert result.stop_distance == Decimal("2000")
    assert result.position_size == Decimal("0.100")
    assert result.required_margin == Decimal("500.00")  # (0.1 * 50,000) / 10
    assert len(result.tp_allocations) == 2

    # TP allocation check (60% / 40%)
    assert result.tp_allocations[0].quantity == Decimal("0.060")
    assert result.tp_allocations[1].quantity == Decimal("0.040")
    assert sum(tp.quantity for tp in result.tp_allocations) == result.position_size


def test_leverage_downscaling_for_wide_sl():
    # Entry 100, SL 50 (50% stop loss!).
    # If user requests 20x leverage, liquidation is at ~5% drop -> user liquidated BEFORE SL!
    # Domain service must downscale leverage to safe level.
    result = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000"),
        entry_price=Decimal("100"),
        sl_price=Decimal("50"),
        risk_percent=Decimal("2.0"),
        requested_leverage=20,
    )

    assert result.is_leverage_downscaled is True
    assert result.leverage < 20
    assert "Downscaled" in result.leverage_adjustment_reason


def test_tp_allocation_rounding_and_sum_integrity():
    # Odd position size (e.g. 0.333 BTC) across 3 TPs
    tps = [Decimal("51000"), Decimal("52000"), Decimal("55000")]
    allocations = RiskCalculatorDomainService.allocate_take_profits(
        total_qty=Decimal("0.333"),
        tp_targets=tps,
        step_size=Decimal("0.001"),
        qty_precision=3,
    )

    assert len(allocations) == 3
    # Total sum must exactly equal 0.333 without floating point loss
    total_allocated = sum(a.quantity for a in allocations)
    assert total_allocated == Decimal("0.333")
    assert allocations[2].is_close_all is True


def test_zero_stop_distance_error():
    with pytest.raises(ZeroStopDistanceError):
        RiskCalculatorDomainService.calculate_position_size(
            wallet_balance=Decimal("1000"),
            entry_price=Decimal("50000"),
            sl_price=Decimal("50000"),
        )


def test_estimated_liquidation_price():
    # BUY: Entry 10,000, 10x leverage -> Liq around ~9,150
    liq_buy = RiskCalculatorDomainService.estimate_liquidation_price(
        entry_price=Decimal("10000"),
        leverage=10,
        side=OrderSide.BUY,
        maint_margin_ratio=Decimal("0.015"),
    )
    assert Decimal("9000") < liq_buy < Decimal("9200")

    # SELL: Entry 10,000, 10x leverage -> Liq around ~10,850
    liq_sell = RiskCalculatorDomainService.estimate_liquidation_price(
        entry_price=Decimal("10000"),
        leverage=10,
        side=OrderSide.SELL,
        maint_margin_ratio=Decimal("0.015"),
    )
    assert Decimal("10800") < liq_sell < Decimal("11000")


def test_geometry_validation_in_risk_calculator():
    from src.domain.exceptions.risk import InvalidSignalGeometryError

    # Invalid BUY: SL above entry
    with pytest.raises(InvalidSignalGeometryError):
        RiskCalculatorDomainService.calculate_position_size(
            wallet_balance=Decimal("1000"),
            entry_price=Decimal("50000"),
            sl_price=Decimal("51000"),
            side="BUY",
        )

    # Invalid SELL: SL below entry
    with pytest.raises(InvalidSignalGeometryError):
        RiskCalculatorDomainService.calculate_position_size(
            wallet_balance=Decimal("1000"),
            entry_price=Decimal("50000"),
            sl_price=Decimal("49000"),
            side="SELL",
        )


def test_position_sizing_with_input_dto():
    from src.domain.entities.risk import PositionSizingInput

    # Clean invocation using single DTO parameter object
    input_dto = PositionSizingInput(
        wallet_balance=Decimal("10000"),
        entry_price=Decimal("50000"),
        sl_price=Decimal("48000"),
        side=OrderSide.BUY,
        risk_percent=Decimal("2.0"),
        requested_leverage=10,
        tp_targets=[Decimal("52000"), Decimal("55000")],
    )

    result = RiskCalculatorDomainService.calculate_position_size(input_dto)
    assert result.is_valid is True
    assert result.position_size == Decimal("0.100")
    assert result.required_margin == Decimal("500.00")


def test_price_deviation_calculation():
    # BUY: Target 100, Current 99 (discount / favorable) -> deviation 0
    dev_favorable_buy = RiskCalculatorDomainService.calculate_price_deviation(
        target_price=Decimal("100"),
        current_price=Decimal("99"),
        side=OrderSide.BUY,
    )
    assert dev_favorable_buy == Decimal("0")

    # BUY: Target 100, Current 101 (1% slippage / unfavorable)
    dev_unfavorable_buy = RiskCalculatorDomainService.calculate_price_deviation(
        target_price=Decimal("100"),
        current_price=Decimal("101"),
        side=OrderSide.BUY,
    )
    assert dev_unfavorable_buy == Decimal("0.01")

    # SELL: Target 100, Current 102 (higher sell / favorable) -> deviation 0
    dev_favorable_sell = RiskCalculatorDomainService.calculate_price_deviation(
        target_price=Decimal("100"),
        current_price=Decimal("102"),
        side=OrderSide.SELL,
    )
    assert dev_favorable_sell == Decimal("0")

    # SELL: Target 100, Current 98 (2% slippage / unfavorable)
    dev_unfavorable_sell = RiskCalculatorDomainService.calculate_price_deviation(
        target_price=Decimal("100"),
        current_price=Decimal("98"),
        side=OrderSide.SELL,
    )
    assert dev_unfavorable_sell == Decimal("0.02")


def test_position_sizing_with_value_objects():
    from src.domain.value_objects.price import Price
    from src.domain.value_objects.quantity import Quantity
    from src.domain.value_objects.leverage import Leverage

    # Passing Value Objects directly
    result = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("10000"),
        entry_price=Price("50000"),
        sl_price=Price("48000"),
        side=OrderSide.BUY,
        requested_leverage=Leverage(10),
        step_size=Quantity("0.001"),
        tp_targets=[Price("52000"), Price("55000")],
    )

    assert result.is_valid is True
    assert result.position_size == Decimal("0.100")
    assert result.leverage == 10


def test_strict_mode_exceptions():
    from src.domain.exceptions.risk import InsufficientMarginRiskError, MaxRiskExceededError
    from src.domain.entities.risk import PositionSizingInput

    # Strict mode: Margin exceeds balance -> InsufficientMarginRiskError
    with pytest.raises(InsufficientMarginRiskError):
        RiskCalculatorDomainService.calculate_position_size(
            PositionSizingInput(
                wallet_balance=Decimal("100"),  # Very small balance
                entry_price=Decimal("50000"),
                sl_price=Decimal("49900"),  # Tiny stop loss -> huge position size!
                side=OrderSide.BUY,
                requested_leverage=1,  # 1x leverage requires full notional
                strict=True,
            )
        )

    # Strict mode: Risk amount exceeds hard cap -> MaxRiskExceededError
    with pytest.raises(MaxRiskExceededError):
        RiskCalculatorDomainService.calculate_position_size(
            PositionSizingInput(
                wallet_balance=Decimal("10000"),
                entry_price=Decimal("50000"),
                sl_price=Decimal("48000"),
                side=OrderSide.BUY,
                risk_percent=Decimal("5.0"),  # 500 USDT risk
                max_risk_amount=Decimal("100"),  # Hard cap 100 USDT
                strict=True,
            )
        )



