"""Unit tests for RiskCalculatorDomainService Auto Margin Capping and Pre-Trade Margin Validation."""

from decimal import Decimal
import pytest

from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.entities.risk import PositionSizingInput, RiskCalculationResultDTO
from src.domain.exceptions.risk import (
    InsufficientMarginRiskError,
    RiskCalculationError,
    ZeroStopDistanceError,
)


def test_normal_trade_sufficient_margin():
    """Positive test: Required margin is within free margin, no capping required."""
    # Wallet balance = 1000 USDT, Risk 2% = 20 USDT, Entry = 100, SL = 98 (Dist = 2, 2%)
    # Raw qty = 20 / 2 = 10 units. Notional = 10 * 100 = 1000 USDT. Leverage = 10x.
    # Required Margin = 100 USDT <= Free Margin 500 USDT.
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("500.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        requested_leverage=10,
        risk_percent=Decimal("2.0"),
        auto_margin_cap=True,
    )

    assert res.is_valid is True
    assert res.is_margin_capped is False
    assert res.position_size == Decimal("10.000")
    assert res.required_margin == Decimal("100.000")
    assert res.risk_amount == Decimal("20.000")
    assert res.warning is None


def test_auto_margin_capping_when_margin_insufficient():
    """Positive test: Required margin (100 USDT) exceeds free margin (50 USDT), lot is auto-capped to 95% buffer."""
    # Free Margin = 50 USDT. Safe buffer 95% = 47.50 USDT.
    # Max allowed notional @ 10x leverage = 475.0 USDT.
    # Capped qty = 475 / 100 = 4.75 units.
    # Capped required margin = (4.75 * 100) / 10 = 47.50 USDT <= 50 USDT.
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("50.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        requested_leverage=10,
        risk_percent=Decimal("2.0"),
        auto_margin_cap=True,
        margin_safety_buffer=Decimal("0.95"),
    )

    assert res.is_valid is True
    assert res.is_margin_capped is True
    assert res.original_position_size == Decimal("10.000")
    assert res.original_required_margin == Decimal("100.000")
    assert res.position_size == Decimal("4.750")
    assert res.required_margin == Decimal("47.500")
    assert res.required_margin <= Decimal("50.0")
    assert "Auto-Capped" in (res.warning or "")


def test_multi_tp_allocations_sum_matches_capped_lot():
    """Positive test: TP allocations accurately distribute the auto-capped position size."""
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("40.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        tp_targets=[Decimal("104.0"), Decimal("108.0"), Decimal("112.0")],
        requested_leverage=10,
        risk_percent=Decimal("2.0"),
        auto_margin_cap=True,
    )

    assert res.is_valid is True
    assert res.is_margin_capped is True
    assert len(res.tp_allocations) == 3
    total_allocated_tp_qty = sum(tp.quantity for tp in res.tp_allocations)
    assert total_allocated_tp_qty == res.position_size


def test_strict_mode_rejects_insufficient_margin():
    """Negative test: When auto_margin_cap=False, insufficient margin raises InsufficientMarginRiskError with metadata."""
    with pytest.raises(InsufficientMarginRiskError) as exc_info:
        RiskCalculatorDomainService.calculate_position_size(
            wallet_balance=Decimal("1000.0"),
            free_margin=Decimal("30.0"),
            entry_price=Decimal("100.0"),
            sl_price=Decimal("98.0"),
            requested_leverage=10,
            risk_percent=Decimal("2.0"),
            auto_margin_cap=False,
            strict=True,
        )

    err = exc_info.value
    assert err.required_margin == Decimal("100.000")
    assert err.available_margin == Decimal("30.0")
    assert Decimal(str(err.shortfall)) == Decimal("70.000")
    assert err.leverage == 10
    assert "Margin tidak mencukupi" in str(err)


def test_non_strict_returns_invalid_when_capping_disabled():
    """Negative test: When auto_margin_cap=False and strict=False, returns is_valid=False with shortfall."""
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("30.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        requested_leverage=10,
        risk_percent=Decimal("2.0"),
        auto_margin_cap=False,
        strict=False,
    )

    assert res.is_valid is False
    assert res.is_margin_capped is False
    assert res.shortfall_margin == Decimal("70.000")
    assert "Margin tidak mencukupi" in (res.warning or "")


def test_capped_lot_below_min_notional_fails():
    """Negative test: Extremely small free margin ($0.20) yields notional below exchange min_notional ($5.0)."""
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("0.20"),  # 95% buffer = $0.19 -> @10x = $1.90 notional < $5.0 min notional
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        requested_leverage=10,
        min_notional=Decimal("5.0"),
        auto_margin_cap=True,
        strict=False,
    )

    assert res.is_valid is False
    assert "batas minimum bursa" in (res.warning or "")


def test_zero_free_margin_fails_gracefully():
    """Negative test: Zero free margin with positive wallet balance fails safely."""
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("1000.0"),
        free_margin=Decimal("0.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("98.0"),
        requested_leverage=10,
        auto_margin_cap=True,
        strict=False,
    )

    assert res.is_valid is False
    assert "Margin tidak mencukupi" in (res.warning or "")


def test_edge_case_ultra_tight_stop_loss():
    """Edge case: Ultra-tight stop loss (0.05% stop distance) generates huge lot that is capped to free margin."""
    # Entry = 2.0000, SL = 1.9990 -> Dist = 0.0010 (0.05%).
    # Risk 2% of $100 = $2.00.
    # Raw uncapped qty = 2.00 / 0.0010 = 2000 units ($4000 notional -> $400 margin @ 10x).
    # With free margin = $15.00:
    # 95% of $15 = $14.25 -> Max notional = $142.50 -> Capped qty = 142.50 / 2 = 71.25 units.
    # Required margin = 71.25 * 2 / 10 = 14.25 USDT <= 15.00 USDT.
    res = RiskCalculatorDomainService.calculate_position_size(
        wallet_balance=Decimal("100.0"),
        free_margin=Decimal("15.0"),
        entry_price=Decimal("2.0000"),
        sl_price=Decimal("1.9990"),
        requested_leverage=10,
        risk_percent=Decimal("2.0"),
        step_size=Decimal("0.01"),
        qty_precision=2,
        auto_margin_cap=True,
    )

    assert res.is_valid is True
    assert res.is_margin_capped is True
    assert res.original_position_size == Decimal("2000.00")
    assert res.position_size == Decimal("71.25")
    assert res.required_margin == Decimal("14.25")
    assert res.required_margin <= Decimal("15.0")


def test_edge_case_falsy_zero_free_margin_and_dto_input():
    """Edge case: Passing PositionSizingInput with available_free_margin = 0."""
    dto_input = PositionSizingInput(
        wallet_balance=Decimal("5000.0"),
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        requested_leverage=10,
        available_free_margin=Decimal("0.0"),
        auto_margin_cap=True,
        strict=False,
    )
    res = RiskCalculatorDomainService.calculate_position_size(dto_input)

    assert res.is_valid is False
    assert "Margin tidak mencukupi" in (res.warning or "")
