"""Unit tests for safe OrderSide and PositionSide enum parsing."""

import pytest
from src.domain.value_objects.side import OrderSide, PositionSide


def test_order_side_standard_strings():
    assert OrderSide.from_str("BUY") == OrderSide.BUY
    assert OrderSide.from_str("buy") == OrderSide.BUY
    assert OrderSide.from_str("LONG") == OrderSide.BUY
    assert OrderSide.from_str("SELL") == OrderSide.SELL
    assert OrderSide.from_str("sell") == OrderSide.SELL
    assert OrderSide.from_str("SHORT") == OrderSide.SELL


def test_order_side_enum_identity():
    assert OrderSide.from_str(OrderSide.BUY) == OrderSide.BUY
    assert OrderSide.from_str(OrderSide.SELL) == OrderSide.SELL


def test_order_side_safe_defaults_and_fallbacks():
    assert OrderSide.from_str("NONE") == OrderSide.BUY
    assert OrderSide.from_str("UNKNOWN") == OrderSide.BUY
    assert OrderSide.from_str("") == OrderSide.BUY
    assert OrderSide.from_str(None, default=OrderSide.SELL) == OrderSide.SELL
    assert OrderSide.from_str("INVALID", default=OrderSide.SELL) == OrderSide.SELL


def test_order_side_invalid_without_default():
    with pytest.raises(ValueError):
        OrderSide.from_str("COMPLETELY_INVALID_SIDE")
    with pytest.raises(ValueError):
        OrderSide.from_str(None)
