from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from src.domain.services.precision_filter import PrecisionFilterDomainService as PrecisionFilterService
from src.domain.services.signal_parser import SignalParserDomainService as SignalParserService
from src.domain.services.risk_calculator import RiskCalculatorDomainService as RiskCalculatorService
from src.domain.exceptions.signal import SignalParseError, InvalidSignalDataError

from src.domain.exceptions.risk import ZeroStopDistanceError


def test_parser_various_telegram_signal_formats():
    """Test extracting parameters from various Telegram signal channel formats."""
    parser = SignalParserService()

    # Format 1: Binance Killers style
    text_bk = """
    #BTC/USDT
    Direction: LONG
    Leverage: Cross 20x
    Entry Zone: 60000 - 60500
    Targets: 61500 - 62500 - 64000
    Stop Loss: 59000
    """
    s1 = parser.parse(text_bk)
    assert s1.is_valid is True
    assert s1.symbol == "BTCUSDT"
    assert s1.side == "BUY"
    assert s1.leverage == 20
    assert s1.entry_min == Decimal("60000")
    assert s1.entry_max == Decimal("60500")
    assert s1.sl_price == Decimal("59000")
    assert len(s1.tp_targets) == 3
    assert s1.tp_targets == [Decimal("61500"), Decimal("62500"), Decimal("64000")]

    # Format 2: Crypto VIP individual TP lines
    text_vip = """
    PAIR: ETH/USDT
    SIGNAL: SHORT
    ENTRY: 3200
    TP1: 3100
    TP2: 3000
    TP3: 2900
    SL: 3350
    LEV: 10x
    """
    s2 = parser.parse(text_vip)
    assert s2.is_valid is True
    assert s2.symbol == "ETHUSDT"
    assert s2.side == "SELL"
    assert s2.entry_min == Decimal("3200")
    assert s2.sl_price == Decimal("3350")
    assert s2.tp_targets == [Decimal("3100"), Decimal("3000"), Decimal("2900")]

    # Format 3: Simple plain text
    text_simple = """
    BUY SOLUSDT
    Entry: 140
    Stop: 135
    Targets: 145, 150
    """
    s3 = parser.parse(text_simple)
    assert s3.is_valid is True
    assert s3.symbol == "SOLUSDT"
    assert s3.side == "BUY"
    assert s3.entry_min == Decimal("140")
    assert s3.sl_price == Decimal("135")
    assert s3.tp_targets == [Decimal("145"), Decimal("150")]


def test_parser_invalid_signal_logical_checks():
    """Test detecting invalid signals and throwing domain exceptions in strict mode."""
    parser = SignalParserService()

    # Invalid BUY: SL is higher than entry
    bad_buy = """
    #BTC/USDT
    BUY
    Entry: 60000
    SL: 61000
    TP: 62000
    """
    res = parser.parse(bad_buy)
    assert res.is_valid is False
    assert "Stop Loss (61000) must be lower than Entry" in res.error_message

    with pytest.raises(InvalidSignalDataError):
        parser.parse(bad_buy, strict=True)

    # Empty text
    with pytest.raises(SignalParseError):
        parser.parse("", strict=True)


def test_risk_calculator_strict_loss_guarantee():
    """Test that calculated position size guarantees loss does not exceed 2.0% of balance."""
    calculator = RiskCalculatorService()

    # Wallet: 10,000 USDT, Risk: 2.0% = 200 USDT
    # Entry: 60,000, SL: 58,000 (Stop distance = 2,000)
    # Expected Qty: 200 / 2,000 = 0.100 BTC
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("10000"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("60000"),
        sl_price=Decimal("58000"),
        leverage=20,
        tp_targets=[Decimal("62000"), Decimal("64000"), Decimal("66000")],
        step_size=Decimal("0.001"),
        qty_precision=3,
    )

    assert res.is_valid is True
    assert res.risk_amount == Decimal("200.0")
    assert res.stop_distance == Decimal("2000")
    assert res.position_size == Decimal("0.100")
    # Potential loss if SL is hit = 0.100 * 2000 = 200 USDT
    assert (res.position_size * res.stop_distance) == Decimal("200.000")
    # Required margin at safe leverage
    assert res.required_margin == (res.position_size * Decimal("60000")) / Decimal(str(res.leverage))
    # Risk-to-reward ratios: (62000-60000)/2000 = 1.0, (64000-60000)/2000 = 2.0, (66000-60000)/2000 = 3.0
    assert res.risk_reward_ratios == [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")]


def test_risk_calculator_zero_or_negative_distance_validation():
    """Test that zero stop distance raises ZeroStopDistanceError."""
    calculator = RiskCalculatorService()

    with pytest.raises(ZeroStopDistanceError):
        calculator.calculate_position_size(
            wallet_balance=Decimal("10000"),
            risk_percent=Decimal("2.0"),
            entry_price=Decimal("60000"),
            sl_price=Decimal("60000"),  # Same as entry
            leverage=20,
        )


def test_risk_calculator_tp_allocations_and_rounding():
    """Test dividing lot size across Take Profit levels with exact remainder conservation."""
    calculator = RiskCalculatorService()

    total_qty = Decimal("0.100")
    tp_targets = [Decimal("61000"), Decimal("62000"), Decimal("63000")]

    allocations = calculator.calculate_tp_allocations(
        total_qty=total_qty,
        tp_targets=tp_targets,
        entry_price=Decimal("60000"),
        step_size=Decimal("0.001"),
        qty_precision=3,
    )

    assert len(allocations) == 3
    # Default 3 TPs: 50%, 30%, 20%
    assert allocations[0].quantity == Decimal("0.050")
    assert allocations[1].quantity == Decimal("0.030")
    assert allocations[2].quantity == Decimal("0.020")
    assert sum(a.quantity for a in allocations) == total_qty
    assert allocations[2].is_close_all is True


def test_precision_filter_lot_and_tick_floor_rounding():
    """Test deterministic floor rounding for lot quantities and tick rounding for prices."""
    # Lot quantity floor rounding
    raw_qty = Decimal("0.123999")
    rounded_qty = PrecisionFilterService.round_quantity(
        raw_qty, step_size=Decimal("0.001"), qty_precision=3, round_down=True
    )
    assert rounded_qty == Decimal("0.123")  # Must be 0.123, NOT 0.124

    # Price tick rounding
    raw_price = Decimal("60000.178")
    rounded_price = PrecisionFilterService.round_price(
        raw_price, tick_size=Decimal("0.1"), price_precision=1
    )
    assert rounded_price == Decimal("60000.2")

    # Leverage clamping
    assert PrecisionFilterService.clamp_leverage(150, max_leverage=125) == 125
    assert PrecisionFilterService.clamp_leverage(-5, min_leverage=1) == 1


def test_precision_filter_min_notional_validation():
    """Test minimum notional order validation."""
    # 60,000 * 0.00005 = 3.0 USDT (< 5.0 min notional)
    assert PrecisionFilterService.validate_min_notional(
        Decimal("60000"), Decimal("0.00005"), min_notional=Decimal("5.0")
    ) is False

    # 60,000 * 0.001 = 60.0 USDT (>= 5.0 min notional)
    assert PrecisionFilterService.validate_min_notional(
        Decimal("60000"), Decimal("0.001"), min_notional=Decimal("5.0")
    ) is True


def test_risk_calculator_dynamic_leverage_and_safe_mmr():
    """Test dynamic leverage downscaling based on stop distance percentage and Binance brackets."""
    calculator = RiskCalculatorService()

    # Mock Binance leverage brackets for AAVEUSDT
    brackets = [
        type("Bracket", (), {
            "bracket": 1,
            "initial_leverage": 50,
            "notional_floor": Decimal("0"),
            "notional_cap": Decimal("5000"),
            "maint_margin_ratio": Decimal("0.015"),
        })(),
        type("Bracket", (), {
            "bracket": 2,
            "initial_leverage": 20,
            "notional_floor": Decimal("5000"),
            "notional_cap": Decimal("25000"),
            "maint_margin_ratio": Decimal("0.025"),
        })(),
    ]

    # Scenario 1: Stop distance 4% (Entry: 100, SL: 96), MMR = 1.5% (Total risk buffer = 5.5%)
    # Max Safe Leverage = 1 / 0.055 = 18x
    # Signal requested 75x -> Should be capped at 18x
    res1 = calculator.calculate_position_size(
        wallet_balance=Decimal("4251.45"),
        risk_percent=Decimal("2.0"),  # Risk amount = 85.029
        entry_price=Decimal("100.0"),
        sl_price=Decimal("96.0"),
        leverage=75,  # Signal asks 75x
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=brackets,
    )

    assert res1.is_valid is True
    assert res1.leverage in (15, 18)
    assert res1.requested_leverage == 75
    assert res1.max_safe_leverage in (15, 18)
    assert res1.is_leverage_downscaled is True
    assert "75x" in res1.leverage_adjustment_reason


    # Scenario 2: Tight stop distance 1% (Entry: 100, SL: 99), MMR = 1.5% (Total risk buffer = 2.5%)
    # Max Safe Leverage = 1 / 0.025 = 40x
    # Bracket Max = 50x. Signal requested 20x.
    # Effective Leverage should stay 20x (not downscaled)
    res2 = calculator.calculate_position_size(
        wallet_balance=Decimal("10000.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("100.0"),
        sl_price=Decimal("99.0"),
        leverage=20,
        step_size=Decimal("0.1"),
        qty_precision=1,
        brackets=brackets,
    )

    assert res2.is_valid is True
    assert res2.leverage == 20
    assert res2.is_leverage_downscaled is False


def test_risk_calculator_uses_precomputed_max_risk_amount():
    """Test that calculate_position_size directly utilizes max_risk_amount from DailyRiskConfig."""
    calculator = RiskCalculatorService()

    # Even if wallet_balance * 2% would be $200, passing max_risk_amount=$150 (from DailyRisk)
    # must directly set risk_amount to $150 and compute position size accordingly.
    # Stop distance = 2,000. Expected Qty = 150 / 2,000 = 0.075 BTC
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("10000"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("60000"),
        sl_price=Decimal("58000"),
        leverage=20,
        step_size=Decimal("0.001"),
        qty_precision=3,
        max_risk_amount=Decimal("150.0"),
    )

    assert res.is_valid is True
    assert res.risk_amount == Decimal("150.0")
    assert res.position_size == Decimal("0.075")
    assert (res.position_size * res.stop_distance) == Decimal("150.000")


def test_risk_calculator_with_bundled_domain_entities():
    """Test that calculate_position_size extracts parameters directly from Domain Entities."""
    from unittest.mock import MagicMock
    calculator = RiskCalculatorService()

    # Mock domain entities
    mock_signal = MagicMock(
        avg_entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=25,
        tp_targets=[Decimal("63000.0"), Decimal("66000.0")],
    )
    mock_instrument = MagicMock(
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        price_precision=2,
        qty_precision=3,
        min_notional=Decimal("5.0"),
        leverage_brackets=[],
    )
    mock_profile = MagicMock(
        risk_percent=Decimal("3.0"),
    )
    mock_daily_risk = MagicMock(
        risk_amount=Decimal("300.0"),
    )

    res = calculator.calculate_position_size(
        wallet_balance=Decimal("10000.0"),
        signal_dto=mock_signal,
        instrument=mock_instrument,
        profile=mock_profile,
        daily_risk=mock_daily_risk,
    )

    assert res.is_valid is True
    assert res.risk_amount == Decimal("300.0")  # extracted from daily_risk
    assert res.entry_price == Decimal("60000.0")  # extracted from signal_dto
    assert res.sl_price == Decimal("58000.0")      # extracted from signal_dto
    assert res.requested_leverage == 25           # extracted from signal_dto
    assert len(res.tp_allocations) == 2           # 2 TP targets from signal_dto


def test_risk_calculator_asymmetric_price_deviation():
    """Test pure calculation of asymmetric price deviations for BUY and SELL."""
    calc = RiskCalculatorService()

    # 1. BUY: Current cheaper than target (Favorable -> 0.0)
    dev_buy_favorable = calc.calculate_price_deviation(
        target_price=Decimal("60000.0"),
        current_price=Decimal("59800.0"),
        side="BUY",
    )
    assert dev_buy_favorable == Decimal("0")

    # 2. BUY: Current more expensive than target (Unfavorable)
    dev_buy_unfavorable = calc.calculate_price_deviation(
        target_price=Decimal("60000.0"),
        current_price=Decimal("60090.0"),
        side="BUY",
    )
    assert dev_buy_unfavorable == Decimal("0.0015")  # +0.15%

    # 3. SELL: Current higher than target (Favorable -> 0.0)
    dev_sell_favorable = calc.calculate_price_deviation(
        target_price=Decimal("60000.0"),
        current_price=Decimal("60500.0"),
        side="SELL",
    )
    assert dev_sell_favorable == Decimal("0")

    # 4. SELL: Current lower than target (Unfavorable)
    dev_sell_unfavorable = calc.calculate_price_deviation(
        target_price=Decimal("60000.0"),
        current_price=Decimal("59400.0"),
        side="SELL",
    )
    assert dev_sell_unfavorable == Decimal("0.01")  # +1.0%


def test_risk_calculator_with_entry_price_override():
    """Test that entry_price override properly calculates sizing using live execution price."""
    calculator = RiskCalculatorService()
    mock_signal = MagicMock(
        avg_entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        tp_targets=[Decimal("63000.0")],
    )
    mock_instrument = MagicMock(
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        price_precision=2,
        qty_precision=3,
        min_notional=Decimal("5.0"),
        leverage_brackets=[],
    )

    # When live market entry is 60,100 (stop_distance = 60100 - 58000 = 2100)
    res = calculator.calculate_position_size(
        wallet_balance=Decimal("10000.0"),
        signal_dto=mock_signal,
        instrument=mock_instrument,
        risk_percent=Decimal("2.0"),  # $200 risk
        entry_price=Decimal("60100.0"),
    )

    assert res.is_valid is True
    assert res.entry_price == Decimal("60100.0")
    assert res.stop_distance == Decimal("2100.0")
    # Position size = 200 / 2100 = 0.095238... rounded to step_size 0.001 = 0.095
    assert res.position_size == Decimal("0.095")




