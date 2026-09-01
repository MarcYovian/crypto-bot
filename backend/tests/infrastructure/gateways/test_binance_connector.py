"""Comprehensive unit tests for BinanceConnector and Domain Exception mapping."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import pytest
import ccxt.async_support as ccxt

from src.infrastructure.gateways.binance import BinanceConnector
from src.domain.exceptions import (
    ExchangeError,
    ExchangeNetworkError,
    ExchangeAuthError,
    InsufficientMarginError,
    OrderRejectError,
    RateLimitError,
)


@pytest.mark.asyncio
async def test_binance_connector_init_and_sandbox_mode():
    """Test initializing BinanceConnector with testnet vs mainnet configuration."""
    testnet_conn = BinanceConnector(api_key="key", secret_key="sec", testnet=True)
    assert testnet_conn.testnet is True

    mainnet_conn = BinanceConnector(api_key="key", secret_key="sec", testnet=False)
    assert mainnet_conn.testnet is False

    await testnet_conn.close()
    await mainnet_conn.close()


@pytest.mark.asyncio
async def test_binance_connector_fetch_instruments_metadata():
    """Test parsing exchange market specifications into Decimal precision metadata."""
    connector = BinanceConnector(testnet=True)

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

    mock_exchange = MagicMock()
    mock_exchange.load_markets = AsyncMock(return_value=mock_markets)
    mock_exchange.markets = mock_markets
    connector.get_rest_exchange = AsyncMock(return_value=mock_exchange)

    metadata = await connector.fetch_instruments_metadata()
    assert len(metadata) == 2

    btc = next(m for m in metadata if m["symbol"] == "BTCUSDT")
    assert btc["base_asset"] == "BTC"
    assert btc["quote_asset"] == "USDT"
    assert btc["price_precision"] == 1
    assert btc["qty_precision"] == 3
    assert btc["tick_size"] == Decimal("0.1")
    assert btc["step_size"] == Decimal("0.001")
    assert btc["min_notional"] == Decimal("5.0")

    await connector.close()


@pytest.mark.asyncio
async def test_binance_connector_fetch_leverage_brackets():
    """Test fetching and parsing Binance Futures leverage brackets via fapiPrivateGetLeverageBracket."""
    connector = BinanceConnector(testnet=True)

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

    mock_exchange = MagicMock()
    mock_exchange.fapiPrivateGetLeverageBracket = AsyncMock(return_value=mock_bracket_data)
    connector.get_rest_exchange = AsyncMock(return_value=mock_exchange)

    results = await connector.fetch_leverage_brackets("AAVEUSDT")
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

    mock_exchange.fapiPrivateGetLeverageBracket.assert_called_with({"symbol": "AAVEUSDT"})
    await connector.close()


@pytest.mark.asyncio
async def test_binance_connector_domain_exceptions_mapping():
    """Test that CCXT raw exceptions are mapped cleanly to custom Domain exceptions."""
    connector = BinanceConnector(testnet=True)
    mock_exchange = MagicMock()
    connector.get_rest_exchange = AsyncMock(return_value=mock_exchange)

    # 1. Insufficient Funds -> InsufficientMarginError
    mock_exchange.fetch_balance = AsyncMock(side_effect=ccxt.InsufficientFunds("Account has insufficient balance"))
    with pytest.raises(InsufficientMarginError):
        await connector.execute_rest("fetch_balance")

    # 2. Authentication Error -> ExchangeAuthError
    mock_exchange.fetch_balance = AsyncMock(side_effect=ccxt.AuthenticationError("API-key format invalid"))
    with pytest.raises(ExchangeAuthError):
        await connector.execute_rest("fetch_balance")

    # 3. Rate Limit Exceeded -> RateLimitError
    mock_exchange.fetch_balance = AsyncMock(side_effect=ccxt.RateLimitExceeded("Too many requests"))
    with pytest.raises(RateLimitError):
        await connector.execute_rest("fetch_balance")

    # 4. Invalid Order -> OrderRejectError
    mock_exchange.create_order = AsyncMock(side_effect=ccxt.InvalidOrder("Order would immediately trigger"))
    with pytest.raises(OrderRejectError):
        await connector.execute_rest("create_order", "BTCUSDT", "market", "buy", 0.1)

    # 5. Network Error -> ExchangeNetworkError
    mock_exchange.fetch_ticker = AsyncMock(side_effect=ccxt.NetworkError("Connection timed out"))
    with pytest.raises(ExchangeNetworkError):
        await connector.execute_rest("fetch_ticker", "BTCUSDT")

    await connector.close()


@pytest.mark.asyncio
async def test_binance_connector_thread_safe_lazy_init():
    """Test that concurrent tasks initialize the rest exchange safely without race condition."""
    connector = BinanceConnector(api_key="key", secret_key="sec", testnet=True)

    # Launch multiple concurrent get_rest_exchange calls
    results = await asyncio.gather(
        connector.get_rest_exchange(),
        connector.get_rest_exchange(),
        connector.get_rest_exchange(),
    )

    # All should return the same singleton instance
    assert results[0] is results[1]
    assert results[1] is results[2]
    await connector.close()
