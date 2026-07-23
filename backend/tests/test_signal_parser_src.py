import pytest
from src.services.signal_parser import SignalParserService, ParsedSignal


def test_parse_kaito_ai_signal():
    text = """🤖 AI Agent Detect Chart Pattern

🚨 Symbol: KAITOUSDT 🟢 Long
⏱ Timeframe: 1H
📈 Leverage: 75x
🔷 Pattern: Rising Wedge(Contracting)

💰 Entry: 1.0468612644
🛡 SL: 0.971579 (-539.34%)
🎯 TP1: 1.1258288506 (+565.75%)
⚡️ TP2: 1.2179577011 (+1225.78%)
🔥 TP3: 1.2301 (+1312.77%)

🧠 Confidence Score (AI): 72%"""

    signal: ParsedSignal = SignalParserService.parse(text)

    assert signal.is_valid is True
    assert signal.symbol == "KAITOUSDT"
    assert signal.side == "BUY"
    assert signal.entry_min == 1.0468612644
    assert signal.entry_max == 1.0468612644
    assert signal.sl_price == 0.971579
    assert signal.tp_prices == [1.1258288506, 1.2179577011, 1.2301]
    assert signal.confidence == 0.72
    assert signal.error_message is None


def test_parse_solana_short_signal():
    text = """🤖 AI Pattern Detector
🚨 Symbol: #SOLUSDT 🔴 Short
💰 Entry Zone: 185.50 - 187.00
🛡 Stop Loss: 191.00
🎯 TP1: 180.00
⚡️ TP2: 175.50
🔥 TP3: 168.00
🧠 Confidence Score (AI): 88%"""

    signal: ParsedSignal = SignalParserService.parse(text)

    assert signal.is_valid is True
    assert signal.symbol == "SOLUSDT"
    assert signal.side == "SELL"
    assert signal.entry_min == 185.50
    assert signal.entry_max == 187.00
    assert signal.sl_price == 191.00
    assert signal.tp_prices == [180.00, 175.50, 168.00]
    assert signal.confidence == 0.88


def test_parse_vip_classic_signal():
    text = """VIP SIGNAL 🚀
PAIR: BTC/USDT
POSITION: LONG
BUY: 64200.5 - 64800.0
SL: 62900.0
TP1: 66000.0
TP2: 67500.0
TP3: 70000.0"""

    signal: ParsedSignal = SignalParserService.parse(text)

    assert signal.is_valid is True
    assert signal.symbol == "BTCUSDT"
    assert signal.side == "BUY"
    assert signal.entry_min == 64200.5
    assert signal.entry_max == 64800.0
    assert signal.sl_price == 62900.0
    assert signal.tp_prices == [66000.0, 67500.0, 70000.0]
    assert signal.confidence is None


def test_parse_invalid_sl_buy():
    text = """Symbol: ADAUSDT 🟢 LONG
Entry: 0.4000
SL: 0.4500
TP1: 0.5000"""

    signal: ParsedSignal = SignalParserService.parse(text)

    assert signal.is_valid is False
    assert signal.error_message == "Invalid SL: Untuk BUY, SL harus di bawah Entry"


def test_parse_non_signal_chat():
    text = "Guys, menurut kalian BTCUSDT malam ini bakal breakout 66k ga?"

    signal: ParsedSignal = SignalParserService.parse(text)

    assert signal.is_valid is False
    assert signal.error_message == "Side (LONG/SHORT) tidak ditemukan"
