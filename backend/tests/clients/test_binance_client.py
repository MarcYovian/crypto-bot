"""Comprehensive unit tests for BinanceRestClient and Domain Exception mapping."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import ccxt.async_support as ccxt
from src.clients.binance_client import BinanceRestClient
from src.domain.exceptions import (
    ExchangeError,
    ExchangeNetworkError,
    ExchangeAuthError,
    InsufficientMarginError,
    OrderRejectError,
    RateLimitError,
)


@pytest.mark.asyncio
async def test_binance_client_init_and_sandbox_mode():
    """Test initializing BinanceRestClient with testnet vs mainnet configuration."""
    testnet_client = BinanceRestClient(api_key="key", secret_key="sec", testnet=True)
    assert testnet_client.testnet is True
    assert testnet_client.client.options["defaultType"] == "future"

    mainnet_client = BinanceRestClient(api_key="key", secret_key="sec", testnet=False)
    assert mainnet_client.testnet is False

    await testnet_client.close()
    await mainnet_client.close()


@pytest.mark.asyncio
async def test_binance_fetch_instruments_metadata_parsing():
    """Test parsing exchange market specifications into Decimal precision metadata."""
    client = BinanceRestClient(testnet=True)

    mock_markets = {
        "BTC/USDT:USDT": {
            "id": "BTCUSDT",
            "base": "BTC",
            "quote": "USDT",
            "active": True,
            "linear": True,
            "precision": {"price": 1, "amount": 3},
            "limits": {
                "price": {"min": 0.1},
                "amount": {"min": 0.001},
                "cost": {"min": 5.0},
            },
        },
        "ETH/USDT:USDT": {
            "id": "ETHUSDT",
            "base": "ETH",
            "quote": "USDT",
            "active": True,
            "linear": True,
            "precision": {"price": 2, "amount": 3},
            "limits": {
                "price": {"min": 0.01},
                "amount": {"min": 0.001},
                "cost": {"min": 5.0},
            },
        },
    }

    client.client.load_markets = AsyncMock(return_value=mock_markets)
    client.client.markets = mock_markets

    metadata = await client.fetch_instruments_metadata()
    assert len(metadata) == 2

    btc = next(m for m in metadata if m["symbol"] == "BTCUSDT")
    assert btc["base_asset"] == "BTC"
    assert btc["quote_asset"] == "USDT"
    assert btc["price_precision"] == 1
    assert btc["qty_precision"] == 3
    assert btc["tick_size"] == Decimal("0.1")
    assert btc["step_size"] == Decimal("0.001")
    assert btc["min_notional"] == Decimal("5.0")

    await client.close()


@pytest.mark.asyncio
async def test_binance_set_leverage_and_margin_mode_idempotency():
    """Test idempotent handling of leverage and margin mode configuration."""
    client = BinanceRestClient(testnet=True)

    # 1. Normal set leverage
    client.client.set_leverage = AsyncMock(return_value={"symbol": "BTCUSDT", "leverage": 20})
    res_lev = await client.set_leverage("BTCUSDT", 20)
    assert res_lev["leverage"] == 20

    # 2. Idempotent set leverage (simulate exception "leverage not modified")
    client.client.set_leverage = AsyncMock(side_effect=Exception("leverage not modified"))
    res_lev_idem = await client.set_leverage("BTCUSDT", 20)
    assert res_lev_idem["leverage"] == 20

    # 3. Normal set margin mode
    client.client.set_margin_mode = AsyncMock(return_value={"symbol": "BTCUSDT", "marginMode": "ISOLATED"})
    res_margin = await client.set_margin_mode("BTCUSDT", "ISOLATED")
    assert res_margin["marginMode"] == "ISOLATED"

    # 4. Idempotent set margin mode (simulate "No need to change margin type")
    client.client.set_margin_mode = AsyncMock(side_effect=Exception("binance -4046 No need to change margin type"))
    res_margin_idem = await client.set_margin_mode("BTCUSDT", "ISOLATED")
    assert res_margin_idem["margin_mode"] == "ISOLATED"

    await client.close()


@pytest.mark.asyncio
async def test_binance_create_entry_and_protection_orders():
    """Test submitting entry, stop-loss, and take-profit orders with correct parameter formatting."""
    client = BinanceRestClient(testnet=True)

    client.client.create_order = AsyncMock(return_value={"id": "bin_order_123", "status": "open"})

    # Entry Market Order
    await client.create_entry_order(
        symbol="BTC/USDT:USDT",
        side="BUY",
        order_type="MARKET",
        qty=Decimal("0.1"),
        client_order_id="ENTRY_01",
    )
    client.client.create_order.assert_called_with(
        symbol="BTC/USDT:USDT",
        type="market",
        side="buy",
        amount=0.1,
        price=None,
        params={"newClientOrderId": "ENTRY_01"},
    )

    # Stop Loss Order
    await client.create_stop_loss_order(
        symbol="BTC/USDT:USDT",
        side="SELL",
        stop_price=Decimal("59000.0"),
        client_order_id="SL_01",
        close_position=True,
    )
    client.client.create_order.assert_called_with(
        symbol="BTC/USDT:USDT",
        type="stop_market",
        side="sell",
        amount=None,
        params={"stopPrice": 59000.0, "closePosition": True, "newClientOrderId": "SL_01"},
    )

    # Take Profit Order
    await client.create_take_profit_order(
        symbol="BTC/USDT:USDT",
        side="SELL",
        tp_price=Decimal("62000.0"),
        qty=Decimal("0.05"),
        client_order_id="TP_01",
    )
    client.client.create_order.assert_called_with(
        symbol="BTC/USDT:USDT",
        type="limit",
        side="sell",
        amount=0.05,
        price=62000.0,
        params={"reduceOnly": True, "newClientOrderId": "TP_01"},
    )

    await client.close()


@pytest.mark.asyncio
async def test_binance_fetch_balance_and_positions():
    """Test fetching balance and active position details with Decimal parsing."""
    client = BinanceRestClient(testnet=True)

    # Mock fetch_balance
    mock_bal = {
        "USDT": {"total": 10000.0, "free": 8500.0, "used": 1500.0},
        "info": {"totalUnrealizedProfit": 250.50},
    }
    client.client.fetch_balance = AsyncMock(return_value=mock_bal)

    balance = await client.fetch_balance()
    assert balance["total_wallet_balance"] == Decimal("10000.0")
    assert balance["free_margin"] == Decimal("8500.0")
    assert balance["used_margin"] == Decimal("1500.0")
    assert balance["unrealized_pnl"] == Decimal("250.50")

    # Mock fetch_positions
    mock_pos = [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "contracts": 0.1,
            "entryPrice": 60000.0,
            "markPrice": 60500.0,
            "unrealizedPnl": 50.0,
            "leverage": 20,
            "liquidationPrice": 57000.0,
        },
        {"symbol": "ETHUSDT", "contracts": 0.0},
    ]
    client.client.fetch_positions = AsyncMock(return_value=mock_pos)

    positions = await client.fetch_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTCUSDT"
    assert positions[0]["contracts"] == Decimal("0.1")
    assert positions[0]["entry_price"] == Decimal("60000.0")

    await client.close()


@pytest.mark.asyncio
async def test_binance_cancel_order_and_cancel_all():
    """Test cancelling individual and bulk orders."""
    client = BinanceRestClient(testnet=True)

    client.client.cancel_order = AsyncMock(return_value={"id": "bin_123", "status": "canceled"})
    client.client.cancel_all_orders = AsyncMock(return_value=[{"status": "canceled"}])

    res1 = await client.cancel_order("BTCUSDT", order_id="bin_123")
    assert res1["status"] == "canceled"
    client.client.cancel_order.assert_called_with(id="bin_123", symbol="BTCUSDT", params={})

    res2 = await client.cancel_all_orders("BTCUSDT")
    assert len(res2) == 1
    client.client.cancel_all_orders.assert_called_with(symbol="BTCUSDT")

    await client.close()


@pytest.mark.asyncio
async def test_binance_domain_exceptions_mapping():
    """Test that CCXT raw exceptions are mapped cleanly to custom Domain exceptions."""
    client = BinanceRestClient(testnet=True)

    # 1. Insufficient Funds -> InsufficientMarginError
    client.client.fetch_balance = AsyncMock(side_effect=ccxt.InsufficientFunds("Account has insufficient balance"))
    with pytest.raises(InsufficientMarginError):
        await client.fetch_balance()

    # 2. Authentication Error -> ExchangeAuthError
    client.client.fetch_balance = AsyncMock(side_effect=ccxt.AuthenticationError("API-key format invalid"))
    with pytest.raises(ExchangeAuthError):
        await client.fetch_balance()

    # 3. Rate Limit Exceeded -> RateLimitError
    client.client.fetch_balance = AsyncMock(side_effect=ccxt.RateLimitExceeded("Too many requests"))
    with pytest.raises(RateLimitError):
        await client.fetch_balance()

    # 4. Invalid Order -> OrderRejectError
    client.client.create_order = AsyncMock(side_effect=ccxt.InvalidOrder("Order would immediately trigger"))
    with pytest.raises(OrderRejectError):
        await client.create_entry_order("BTCUSDT", "BUY", "MARKET", Decimal("0.1"))

    # 5. Network Error -> ExchangeNetworkError
    client.client.fetch_ticker = AsyncMock(side_effect=ccxt.NetworkError("Connection timed out"))
    with pytest.raises(ExchangeNetworkError):
        await client.fetch_ticker_price("BTCUSDT")

    await client.close()


@pytest.mark.asyncio
async def test_binance_fetch_leverage_brackets():
    """Test fetching and parsing Binance Futures leverage brackets."""
    client = BinanceRestClient(testnet=True)

    mock_bracket_data = [
        {
            "symbol": "AAVEUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 50,
                    "notionalCap": 5000,
                    "notionalFloor": 0,
                    "maintMarginRatio": 0.015,
                    "cum": 0.0,
                },
                {
                    "bracket": 2,
                    "initialLeverage": 20,
                    "notionalCap": 25000,
                    "notionalFloor": 5000,
                    "maintMarginRatio": 0.025,
                    "cum": 50.0,
                },
            ],
        }
    ]

    client.client.fapiPrivateGetLeverageBracket = AsyncMock(return_value=mock_bracket_data)

    results = await client.fetch_leverage_brackets("AAVEUSDT")
    assert len(results) == 1
    assert results[0]["symbol"] == "AAVEUSDT"
    brackets = results[0]["brackets"]
    assert len(brackets) == 2
    assert brackets[0]["bracket"] == 1
    assert brackets[0]["initial_leverage"] == 50
    assert brackets[0]["notional_cap"] == Decimal("5000")
    assert brackets[0]["maint_margin_ratio"] == Decimal("0.015")
    assert brackets[1]["bracket"] == 2
    assert brackets[1]["initial_leverage"] == 20

    client.client.fapiPrivateGetLeverageBracket.assert_called_with({"symbol": "AAVEUSDT"})
    await client.close()


@pytest.mark.asyncio
async def test_binance_fetch_open_orders():
    """Test fetching and parsing open orders from Binance Futures."""
    client = BinanceRestClient(testnet=True)

    mock_open_orders = [
        {
            "id": "12345678",
            "clientOrderId": "TP1_1_999",
            "symbol": "BTC/USDT:USDT",
            "type": "LIMIT",
            "side": "SELL",
            "price": 62000.0,
            "stopPrice": None,
            "amount": 0.05,
            "filled": 0.0,
            "remaining": 0.05,
            "status": "open",
            "reduceOnly": True,
            "timestamp": 1700000000000,
        },
        {
            "id": "87654321",
            "clientOrderId": "SL_1_999",
            "symbol": "BTC/USDT:USDT",
            "type": "STOP_MARKET",
            "side": "SELL",
            "price": None,
            "stopPrice": 58000.0,
            "amount": 0.1,
            "filled": 0.0,
            "remaining": 0.1,
            "status": "open",
            "reduceOnly": True,
            "timestamp": 1700000000000,
        },
    ]

    client.client.fetch_open_orders = AsyncMock(return_value=mock_open_orders)

    orders = await client.fetch_open_orders("BTCUSDT")
    assert len(orders) == 2
    assert orders[0]["id"] == "12345678"
    assert orders[0]["symbol"] == "BTCUSDT"
    assert orders[0]["side"] == "SELL"
    assert orders[0]["price"] == Decimal("62000")
    assert orders[0]["amount"] == Decimal("0.05")
    assert orders[0]["reduce_only"] is True

    assert orders[1]["id"] == "87654321"
    assert orders[1]["stop_price"] == Decimal("58000")
    assert orders[1]["amount"] == Decimal("0.1")

    client.client.fetch_open_orders.assert_called_with(symbol="BTCUSDT")
    await client.close()


@pytest.mark.asyncio
async def test_binance_fetch_order():
    """Test fetching a single order status by ID from Binance."""
    client = BinanceRestClient(testnet=True)

    mock_single_order = {
        "id": "12345678",
        "clientOrderId": "TP1_1_999",
        "symbol": "BTC/USDT:USDT",
        "type": "LIMIT",
        "side": "SELL",
        "price": 62000.0,
        "amount": 0.05,
        "filled": 0.05,
        "remaining": 0.0,
        "status": "closed",
        "reduceOnly": True,
        "timestamp": 1700000000000,
    }

    client.client.fetch_order = AsyncMock(return_value=mock_single_order)

    order = await client.fetch_order("BTCUSDT", "12345678")
    assert order is not None
    assert order["id"] == "12345678"
    assert order["status"] == "CLOSED"
    assert order["filled"] == Decimal("0.05")
    assert order["remaining"] == Decimal("0.0")

    client.client.fetch_order.assert_called_with(id="12345678", symbol="BTCUSDT")
    await client.close()


