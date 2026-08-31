"""Unit tests for domain Value Objects."""

from decimal import Decimal
import pytest

from src.domain.value_objects.symbol import Symbol
from src.domain.value_objects.side import OrderSide, PositionSide, MarginMode
from src.domain.value_objects.trade_status import TradeStatus, OrderStatus, OrderPurpose
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity
from src.domain.value_objects.leverage import Leverage
from src.domain.value_objects.entry_zone import TakeProfitTarget, EntryZone, TradeGeometry
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    InvalidSignalGeometryError,
)


def test_symbol_normalization():
    sym1 = Symbol("BTC/USDT")
    assert sym1.value == "BTCUSDT"
    assert sym1.base_asset == "BTC"
    assert sym1.quote_asset == "USDT"

    sym2 = Symbol("eth-usdt:usdt")
    assert sym2.value == "ETHUSDT"
    assert sym2.base_asset == "ETH"
    assert sym2.quote_asset == "USDT"

    sym3 = Symbol.from_str("SOLUSDC")
    assert sym3.base_asset == "SOL"
    assert sym3.quote_asset == "USDC"

    # Equivalence check
    assert sym1 == "BTCUSDT"
    assert sym1 == Symbol("BTCUSDT")

    # Invalid symbol
    with pytest.raises(ValueError):
        Symbol("$$$")


def test_side_enums():
    buy = OrderSide.from_str("BUY")
    assert buy.is_buy is True
    assert buy.is_sell is False
    assert buy.opposite == OrderSide.SELL

    sell = OrderSide.from_str("SHORT")
    assert sell.is_sell is True
    assert sell.opposite == OrderSide.BUY

    pos = PositionSide.from_str("long")
    assert pos == PositionSide.LONG

    margin = MarginMode.from_str("cross")
    assert margin == MarginMode.CROSSED


def test_trade_and_order_statuses():
    st = TradeStatus.from_str("WAITING_ENTRY")
    assert st.is_active is True
    assert st.is_terminal is False

    open_st = TradeStatus.from_str("open")
    assert open_st.is_open_position is True

    closed_st = TradeStatus.from_str("closed")
    assert closed_st.is_terminal is True

    ord_st = OrderStatus.from_str("FILLED")
    assert ord_st.is_filled is True
    assert ord_st.is_terminal is True

    # OrderStatus CANCELED vs CANCELLED alias tests
    assert OrderStatus.CANCELED == OrderStatus.CANCELLED
    assert OrderStatus.CANCELLED is OrderStatus.CANCELED
    assert OrderStatus.CANCELLED.value == "CANCELED"
    assert OrderStatus.from_str("CANCELLED") == OrderStatus.CANCELED
    assert OrderStatus.from_str("canceled") == OrderStatus.CANCELED
    assert OrderStatus.CANCELLED.is_terminal is True
    assert OrderStatus.CANCELED.is_terminal is True

    # Order Purpose tests
    purp = OrderPurpose.from_str("TP1")
    assert purp == OrderPurpose.TP1
    assert purp.is_tp is True

    bep = OrderPurpose.from_str("BEP_SL")
    assert bep == OrderPurpose.BEP_SL
    assert bep.is_bep is True
    assert bep.is_sl is True

    trailing = OrderPurpose.from_str("TRAILING_SL")
    assert trailing.is_trailing is True
    assert trailing.is_sl is True

    # Order Type tests
    from src.domain.value_objects.trade_status import OrderType

    market = OrderType.from_str("MARKET")
    assert market.is_market is True
    assert market.is_limit is False

    limit = OrderType.from_str("LIMIT")
    assert limit.is_limit is True

    stop_mkt = OrderType.from_str("STOP_MARKET")
    assert stop_mkt.is_stop is True
    assert stop_mkt.is_market is True

    tp_mkt = OrderType.from_str("TAKE_PROFIT_MARKET")
    assert tp_mkt.is_take_profit is True

    trailing_mkt = OrderType.from_str("TRAILING_STOP_MARKET")
    assert trailing_mkt.is_stop is True



def test_price_value_object():
    p1 = Price("50000.1234")
    p2 = Price(50000)
    assert p1 > p2
    assert p1 + Decimal("100") == Price("50100.1234")
    assert p1 - Decimal("100") == Price("49900.1234")

    # Round to tick size
    rounded = p1.round_to_tick(Decimal("0.1"))
    assert rounded == Price("50000.1")

    rounded_05 = p1.round_to_tick(Decimal("0.05"))
    assert rounded_05 == Price("50000.10")

    # Negative price rejected
    with pytest.raises(ValueError):
        Price("-10")


def test_quantity_value_object():
    q = Quantity("1.23456")
    # Floor round to step_size 0.001
    q_floored = q.round_to_step(Decimal("0.001"), mode="floor")
    assert q_floored == Quantity("1.234")

    q_half_up = q.round_to_step(Decimal("0.001"), mode="half_up")
    assert q_half_up == Quantity("1.235")

    with pytest.raises(ValueError):
        Quantity("-1")


def test_leverage_value_object():
    lev = Leverage(20)
    assert lev.as_int() == 20
    assert lev.validate_against_bracket(max_bracket_leverage=50) is True
    assert lev.validate_against_bracket(max_bracket_leverage=10) is False

    capped = lev.cap_at(max_allowed=15)
    assert capped.value == 15

    with pytest.raises(ValueError):
        Leverage(0)

    with pytest.raises(ValueError):
        Leverage(200)


def test_trade_geometry_validation():
    # Valid BUY
    geom_buy = TradeGeometry(
        side=OrderSide.BUY,
        entry_price=Price("60000"),
        sl_price=Price("58000"),
        tp_targets=[
            TakeProfitTarget(1, Price("62000"), Decimal("50")),
            TakeProfitTarget(2, Price("65000"), Decimal("50")),
        ],
    )
    assert geom_buy.stop_distance == Decimal("2000")
    assert geom_buy.risk_reward_ratio_tp1 == Decimal("1.0")
    assert geom_buy.risk_reward_ratios == [Decimal("1.0"), Decimal("2.5")]


    # Invalid BUY with SL >= Entry
    with pytest.raises(InvalidSignalGeometryError):
        TradeGeometry(
            side=OrderSide.BUY,
            entry_price=Price("60000"),
            sl_price=Price("61000"),
        )

    # Invalid BUY with TP <= Entry
    with pytest.raises(InvalidSignalGeometryError):
        TradeGeometry(
            side=OrderSide.BUY,
            entry_price=Price("60000"),
            sl_price=Price("58000"),
            tp_targets=[TakeProfitTarget(1, Price("59000"))],
        )

    # Valid SELL
    geom_sell = TradeGeometry(
        side=OrderSide.SELL,
        entry_price=Price("60000"),
        sl_price=Price("62000"),
        tp_targets=[TakeProfitTarget(1, Price("58000"))],
    )
    assert geom_sell.stop_distance == Decimal("2000")

    # Zero stop distance
    with pytest.raises(ZeroStopDistanceError):
        TradeGeometry(
            side=OrderSide.BUY,
            entry_price=Price("60000"),
            sl_price=Price("60000"),
        )
