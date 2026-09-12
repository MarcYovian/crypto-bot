# tests/test_error_parser.py
import pytest
from src.utils.error_parser import ErrorParser, FormattedError


def test_parse_insufficient_margin_error():
    raw_error = "binanceusdm {\"code\":-2019,\"msg\":\"Margin is insufficient.\"}"
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "BALANCE"
    assert "INSUFFICIENT BALANCE" in result.title
    assert "[-2019]" in result.code
    
    markdown = result.to_telegram_markdown(symbol="SOLUSDT", side="BUY")
    assert "🔴 *EXECUTION FAILED — INSUFFICIENT BALANCE*" in markdown
    assert "Pair: `SOLUSDT` (BUY)" in markdown


def test_parse_max_quantity_exceeded_error():
    raw_error = "binanceusdm {\"code\":-4005,\"msg\":\"Quantity greater than max quantity.\"}"
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "EXCHANGE"
    assert "EXCHANGE LIMIT" in result.title
    assert "[-4005]" in result.code

    markdown = result.to_telegram_markdown(symbol="JUPUSDT", side="LONG")
    assert "⛔️ *EXECUTION FAILED — EXCHANGE LIMIT*" in markdown
    assert "JUPUSDT" in markdown


def test_parse_precision_error():
    raw_error = "binanceusdm {\"code\":-1111,\"msg\":\"Precision is over the maximum defined for this asset.\"}"
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "EXCHANGE"
    assert "[-1111]" in result.code
    assert "PRECISION" in result.title


def test_parse_risk_identical_sl_error():
    raw_error = "Entry and Stop Loss prices cannot be identical."
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "RISK"
    assert "RISK MANAGEMENT" in result.title
    assert "identical" in result.message


def test_parse_min_notional_error():
    raw_error = "Nilai Notional ($3.20) di bawah MIN_NOTIONAL ($5.0)"
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "RISK"
    assert "MINIMUM NOTIONAL" in result.title
    assert "$5.0" in result.message


def test_parse_unhandled_system_error():
    raw_error = "Database timeout error while fetching open trades"
    result: FormattedError = ErrorParser.parse_error(raw_error)

    assert result.category == "SYSTEM"
    assert "SYSTEM ERROR" in result.title
    assert "Database timeout" in result.message
