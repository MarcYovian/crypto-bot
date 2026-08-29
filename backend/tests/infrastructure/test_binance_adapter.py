"""Unit tests for BinanceExchangeAdapter and its subcomponents."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.domain.value_objects.side import OrderSide, MarginMode
from src.domain.value_objects.trade_status import OrderType, OrderStatus
from src.infrastructure.gateways.binance import (
    BinanceConnector,
    BinanceParser,
    BinanceValidator,
    BinanceExchangeAdapter,
)


@pytest.fixture
def mock_connector():
    connector = MagicMock(spec=BinanceConnector)
    connector.execute_rest = AsyncMock()
    connector.close = AsyncMock()
    return connector


def test_binance_parser_balance():
    raw_ccxt = {
        "info": {"totalWalletBalance": "10500.50", "availableBalance": "9500.00"},
        "USDT": {"total": 10500.50, "free": 9500.00, "used": 1000.50},
    }
    parsed = BinanceParser.parse_balance(raw_ccxt)
    assert parsed["total_wallet_balance"] == Decimal("10500.50")
    assert parsed["free_margin"] == Decimal("9500.00")
    assert parsed["used_margin"] == Decimal("1000.50")


def test_binance_parser_order():
    raw_ccxt_order = {
        "id": "12345678",
        "clientOrderId": "cl_ord_1",
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "type": "limit",
        "status": "closed",
        "price": 65000.0,
        "amount": 0.5,
        "filled": 0.5,
        "remaining": 0.0,
        "average": 65000.0,
        "fee": {"cost": 1.25, "currency": "USDT"},
    }
    parsed = BinanceParser.parse_order(raw_ccxt_order)
    assert parsed["exchange_order_id"] == "12345678"
    assert parsed["symbol"] == "BTCUSDT"
    assert parsed["side"] == OrderSide.BUY
    assert parsed["order_type"] == OrderType.LIMIT
    assert parsed["status"] == OrderStatus.FILLED
    assert parsed["qty"] == Decimal("0.5")
    assert parsed["fee"] == Decimal("1.25")

    # Partially filled order
    raw_partial_order = {
        "id": "12345679",
        "clientOrderId": "cl_ord_2",
        "symbol": "BTC/USDT:USDT",
        "side": "sell",
        "type": "limit",
        "status": "partially_filled",
        "price": 66000.0,
        "amount": 1.0,
        "filled": 0.3,
        "remaining": 0.7,
        "average": 66000.0,
    }
    parsed_partial = BinanceParser.parse_order(raw_partial_order)
    assert parsed_partial["status"] == OrderStatus.PARTIALLY_FILLED
    assert parsed_partial["filled_qty"] == Decimal("0.3")



def test_binance_validator():
    # Valid order
    BinanceValidator.validate_order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=Decimal("0.1"),
        price=Decimal("60000"),
    )

    # Invalid qty
    with pytest.raises(ValueError, match="strictly positive"):
        BinanceValidator.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=Decimal("0"),
        )

    # Missing price for limit order
    with pytest.raises(ValueError, match="Price is strictly required"):
        BinanceValidator.validate_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=Decimal("0.1"),
            price=None,
        )


@pytest.mark.asyncio
async def test_binance_adapter_create_order(mock_connector):
    mock_connector.execute_rest.return_value = {
        "id": "999001",
        "clientOrderId": "bot_entry_1",
        "symbol": "ETH/USDT:USDT",
        "side": "buy",
        "type": "market",
        "status": "open",
        "price": None,
        "amount": 1.0,
        "filled": 0.0,
        "remaining": 1.0,
        "average": None,
    }

    adapter = BinanceExchangeAdapter(connector=mock_connector)
    result = await adapter.create_order(
        symbol="ETHUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty=Decimal("1.0"),
    )

    assert result["exchange_order_id"] == "999001"
    assert result["symbol"] == "ETHUSDT"
    assert result["side"] == OrderSide.BUY
    assert result["status"] == OrderStatus.NEW
    mock_connector.execute_rest.assert_awaited_once()


@pytest.mark.asyncio
async def test_binance_adapter_fetch_ticker(mock_connector):
    mock_connector.execute_rest.return_value = {
        "symbol": "BTC/USDT:USDT",
        "last": 65400.0,
        "bid": 65399.0,
        "ask": 65401.0,
        "high": 66000.0,
        "low": 64000.0,
        "baseVolume": 15000.0,
        "timestamp": 1700000000000,
    }

    adapter = BinanceExchangeAdapter(connector=mock_connector)
    ticker = await adapter.fetch_ticker("BTCUSDT")

    assert ticker["symbol"] == "BTCUSDT"
    assert ticker["last_price"] == Decimal("65400.0")
    assert ticker["bid"] == Decimal("65399.0")


def test_binance_connector_reconfigure():
    connector = BinanceConnector(api_key="initial_key", secret_key="initial_secret", testnet=True)
    assert connector.api_key == "initial_key"
    assert connector.testnet is True

    # Reconfigure dynamically from database credentials
    connector.reconfigure(api_key="new_key", secret_key="new_secret", testnet=False)
    assert connector.api_key == "new_key"
    assert connector.secret_key == "new_secret"
    assert connector.testnet is False


@pytest.mark.asyncio
async def test_binance_adapter_fetch_instruments_metadata():
    mock_connector = MagicMock(spec=BinanceConnector)
    mock_connector.fetch_instruments_metadata = AsyncMock(return_value=[
        {"symbol": "BTCUSDT", "base_asset": "BTC", "quote_asset": "USDT", "price_precision": 1, "qty_precision": 3}
    ])

    adapter = BinanceExchangeAdapter(connector=mock_connector)
    meta = await adapter.fetch_instruments_metadata()
    assert len(meta) == 1
    assert meta[0]["symbol"] == "BTCUSDT"
    mock_connector.fetch_instruments_metadata.assert_awaited_once()


@pytest.mark.asyncio
async def test_binance_adapter_fetch_leverage_brackets():
    mock_connector = MagicMock(spec=BinanceConnector)
    mock_connector.fetch_leverage_brackets = AsyncMock(return_value=[
        {
            "symbol": "BTCUSDT",
            "brackets": [
                {"bracket": 1, "initialLeverage": 125, "notionalCap": 50000, "maintMarginRatio": 0.004, "cum": 0}
            ],
        }
    ])

    adapter = BinanceExchangeAdapter(connector=mock_connector)
    brackets = await adapter.fetch_leverage_brackets("BTCUSDT")
    assert len(brackets) == 1
    assert brackets[0]["symbol"] == "BTCUSDT"
    assert brackets[0]["initial_leverage"] == 125
    mock_connector.fetch_leverage_brackets.assert_awaited_once_with("BTCUSDT")


@pytest.mark.asyncio
async def test_binance_adapter_process_ws_order_event():
    mock_connector = MagicMock(spec=BinanceConnector)
    adapter = BinanceExchangeAdapter(connector=mock_connector)

    mock_uc = AsyncMock()
    mock_uc.execute_from_raw_event = AsyncMock(return_value={"status": "FILLED"})

    raw_event = {"id": "123", "status": "closed"}
    res = await adapter.process_ws_order_event(raw_event, handle_fill_use_case=mock_uc)
    assert res == {"status": "FILLED"}
    mock_uc.execute_from_raw_event.assert_awaited_once_with(raw_event)


