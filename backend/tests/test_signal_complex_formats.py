"""Tests for complex Telegram signal formats, noisy promotional filtering, and price logic validation."""

import pytest
from decimal import Decimal
from src.services.signal_parser import SignalParserService
from src.domain.exceptions.signal import SignalParseError, InvalidSignalDataError


@pytest.fixture
def parser():
    return SignalParserService()


def test_parse_range_entry_long_signal(parser: SignalParserService):
    """Test parsing a LONG signal with entry range (e.g. 50000 - 51000)."""
    raw = """
    🚀 VIP PREMIUM SIGNAL 🚀
    PAIR: #BTC/USDT (LONG)
    LEVERAGE: CROSS 20x
    
    ENTRY ZONE: 50,000 - 51,000
    
    TARGET 1: 52,500
    TARGET 2: 54,000
    TARGET 3: 56,000
    
    STOP LOSS: 48,500
    
    Join our VIP for 95% winrate! t.me/cryptovip
    """
    res = parser.parse(raw)
    assert res.is_valid is True
    assert res.symbol == "BTCUSDT"
    assert res.side == "BUY"
    assert res.leverage == 20
    assert res.entry_min == Decimal("50000")
    assert res.entry_max == Decimal("51000")
    assert res.sl_price == Decimal("48500")
    assert len(res.tp_targets) == 3
    assert res.tp_targets[0] == Decimal("52500")
    assert res.order_type == "LIMIT"


def test_parse_short_signal_slash_separated_tps(parser: SignalParserService):
    """Test parsing a SHORT signal with single line slash-separated targets."""
    raw = """
    📉 SHORT #ETHUSDT
    Lev: 10x
    Entry: 3000
    Stoploss: 3200
    Targets: 2900 / 2800 / 2700
    """
    res = parser.parse(raw)
    assert res.is_valid is True
    assert res.symbol == "ETHUSDT"
    assert res.side == "SELL"
    assert res.leverage == 10
    assert res.entry_min == Decimal("3000")
    assert res.sl_price == Decimal("3200")
    assert len(res.tp_targets) == 3
    assert res.tp_targets[0] == Decimal("2900")
    assert res.tp_targets[1] == Decimal("2800")
    assert res.tp_targets[2] == Decimal("2700")


def test_parse_noisy_promotional_text_filtering(parser: SignalParserService):
    """Test extracting signal accurately despite heavy noise, ads, and disclaimer text."""
    raw = """
    🔥 EXCLUSIVE GEM ALERT 🔥
    Sponsored by CryptoWhale Academy 🎓
    ➖➖➖➖➖➖
    Coin: SOL/USDT
    Direction: BUY 🟢
    Entry: 140.50
    SL: 132.00
    TP1: 150.00
    TP2: 165.00
    Leverage: 15X
    ➖➖➖➖➖➖
    Risk Warning: Trading crypto futures involves high risk. Always use 2% risk management.
    Admin Contact: @whalesupport
    """
    res = parser.parse(raw)
    assert res.is_valid is True
    assert res.symbol == "SOLUSDT"
    assert res.side == "BUY"
    assert res.leverage == 15
    assert res.entry_min == Decimal("140.50")
    assert res.sl_price == Decimal("132.00")
    assert len(res.tp_targets) == 2


def test_parse_invalid_price_logic_buy_sl_above_entry(parser: SignalParserService):
    """Test logical validation: BUY signal with SL above entry is invalid."""
    raw = """
    #BTCUSDT BUY
    Entry: 50000
    SL: 51000
    TP1: 55000
    """
    res = parser.parse(raw)
    assert res.is_valid is False
    assert "must be lower than Entry" in str(res.error_message)


def test_parse_invalid_price_logic_sell_sl_below_entry(parser: SignalParserService):
    """Test logical validation: SELL signal with SL below entry is invalid."""
    raw = """
    #BTCUSDT SELL
    Entry: 50000
    SL: 48000
    TP1: 45000
    """
    res = parser.parse(raw)
    assert res.is_valid is False
    assert "must be higher than Entry" in str(res.error_message)


def test_parse_strict_mode_exceptions(parser: SignalParserService):
    """Test strict=True raises SignalParseError or InvalidSignalDataError."""
    with pytest.raises(SignalParseError):
        parser.parse("Just chatting, no signal here", strict=True)

    with pytest.raises(InvalidSignalDataError):
        parser.parse("""
        #BTCUSDT BUY
        Entry: 50000
        SL: 52000
        TP1: 55000
        """, strict=True)
