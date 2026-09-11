"""Unit tests for GatewayCacheLogger across 5 dimensions:
1. Positif (Happy Path)
2. Negatif (Error Handling / Fault Tolerance)
3. Edge (Symbol Parsing Varieties, Concurrency)
4. Business/Logic (REQ-RES Correlation, Latency Tracking, Multi-Gateway Names)
5. Security (Secret Masking in REST Arguments, Path Sanitization)
"""

import asyncio
import os
import shutil
import tempfile
from decimal import Decimal

import pytest

from src.utils.file_cache.gateway_cache import (
    GatewayCacheLogger,
    extract_symbol_from_args,
)


@pytest.fixture
def temp_gateway_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_gateway_cache_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 1. POSITIF (HAPPY PATH)
# ==============================================================================
@pytest.mark.asyncio
async def test_gateway_write_and_read_request_cache(temp_gateway_dir):
    """Positif: Write and read back a REST request cache file."""
    logger = GatewayCacheLogger(
        gateway_name="binance",
        rest_base_path=temp_gateway_dir,
        chat_id="12345",
    )
    timestamp_str = "20260904120000111222"
    args = ("BTC/USDT", "market", "buy", 0.5)
    kwargs = {"params": {"reduceOnly": False}}

    path = await logger.write_request_cache(
        method_name="create_order",
        args=args,
        kwargs=kwargs,
        timestamp_str=timestamp_str,
        symbol="BTCUSDT",
    )

    assert os.path.exists(path)
    assert path.endswith("20260904120000111222_BTCUSDT_create_order_REQ.json")

    read_back = await logger.read_request_cache(
        timestamp_str=timestamp_str,
        symbol="BTCUSDT",
        method_name="create_order",
    )
    assert read_back is not None
    assert read_back["method"] == "create_order"
    assert read_back["symbol"] == "BTCUSDT"
    assert read_back["args"] == list(args)
    assert read_back["kwargs"]["params"]["reduceOnly"] is False


@pytest.mark.asyncio
async def test_gateway_write_and_read_response_cache(temp_gateway_dir):
    """Positif: Write and read back a REST response cache file."""
    logger = GatewayCacheLogger(
        gateway_name="binance",
        rest_base_path=temp_gateway_dir,
        chat_id="12345",
    )
    timestamp_str = "20260904120000111222"
    res_data = {
        "id": "987654321",
        "symbol": "BTC/USDT",
        "status": "closed",
        "price": Decimal("65000.50"),
        "amount": Decimal("0.5"),
    }

    path = await logger.write_response_cache(
        method_name="create_order",
        response_data=res_data,
        timestamp_str=timestamp_str,
        symbol="BTCUSDT",
        duration_ms=125.4,
    )

    assert os.path.exists(path)
    assert path.endswith("20260904120000111222_BTCUSDT_create_order_RES.json")

    read_back = await logger.read_response_cache(
        timestamp_str=timestamp_str,
        symbol="BTCUSDT",
        method_name="create_order",
    )
    assert read_back is not None
    assert read_back["duration_ms"] == 125.4
    assert read_back["response"]["id"] == "987654321"
    assert read_back["response"]["price"] == "65000.50"


@pytest.mark.asyncio
async def test_gateway_write_and_read_ws_event(temp_gateway_dir):
    """Positif: Write and read WebSocket order event cache file."""
    logger = GatewayCacheLogger(
        gateway_name="binance",
        ws_base_path=temp_gateway_dir,
        chat_id="12345",
    )
    ws_event = {
        "e": "ORDER_TRADE_UPDATE",
        "id": "555111",
        "symbol": "ETHUSDT",
        "side": "BUY",
    }

    path = await logger.write_ws_event_cache(ws_event, tag="WSLISTENER")
    assert os.path.exists(path)
    assert "_555111_WSLISTENER.json" in path

    read_back = await logger.read_ws_event_cache(path)
    assert read_back is not None
    assert read_back["chat_id"] == "12345"
    assert read_back["tag"] == "WSLISTENER"
    assert read_back["data"]["id"] == "555111"


@pytest.mark.asyncio
async def test_gateway_archive_rest_and_ws(temp_gateway_dir):
    """Positif: Test archiving REST and WS directories using GatewayCacheLogger.archive()."""
    rest_base = os.path.join(temp_gateway_dir, "rest")
    ws_base = os.path.join(temp_gateway_dir, "ws")

    logger = GatewayCacheLogger(
        gateway_name="binance",
        rest_base_path=rest_base,
        ws_base_path=ws_base,
        chat_id="12345",
    )

    # Write a rest file and a ws file
    await logger.write_request_cache("test_req", (), {}, "20260904120000", "BTCUSDT")
    await logger.write_ws_event_cache({"id": "100"}, tag="WSLISTENER")

    results = await logger.archive(scope="all")
    assert len(results) == 2
    types = {r["type"] for r in results}
    assert "rest" in types
    assert "ws" in types

    # Verify original cache dirs are cleaned
    assert len(os.listdir(logger.rest_cache_dir)) == 0
    assert len(os.listdir(logger.ws_cache_dir)) == 0


# ==============================================================================
# 2. NEGATIF (ERROR HANDLING & FAULT TOLERANCE)
# ==============================================================================
@pytest.mark.asyncio
async def test_gateway_read_missing_request_or_response(temp_gateway_dir):
    """Negatif: Reading non-existent request/response cache returns None safely."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir)
    res = await logger.read_request_cache("99999999999999", "NONE", "no_method")
    assert res is None


@pytest.mark.asyncio
async def test_gateway_write_empty_or_none_ws(temp_gateway_dir):
    """Negatif: Passing None or empty dict to write_ws_event_cache returns empty string."""
    logger = GatewayCacheLogger(gateway_name="binance", ws_base_path=temp_gateway_dir)
    assert await logger.write_ws_event_cache(None) == ""
    assert await logger.write_ws_event_cache({}) == ""


@pytest.mark.asyncio
async def test_gateway_write_error_response(temp_gateway_dir):
    """Negatif: Recording exchange error response logs error string and None response payload."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir, chat_id="12345")
    timestamp_str = "20260904120000333444"

    path = await logger.write_response_cache(
        method_name="create_order",
        response_data=None,
        timestamp_str=timestamp_str,
        symbol="SOLUSDT",
        duration_ms=45.2,
        error="BinanceExchangeError: Margin is insufficient (-2019)",
    )

    assert os.path.exists(path)
    content = await logger.read_response_cache(timestamp_str, "SOLUSDT", "create_order")
    assert content is not None
    assert content["response"] is None
    assert "insufficient" in content["error"]
    assert content["duration_ms"] == 45.2


# ==============================================================================
# 3. EDGE (SYMBOL EXTRACTION & CONCURRENCY)
# ==============================================================================
def test_gateway_symbol_extraction_varieties():
    """Edge: Test extracting symbol from CCXT linear futures, spots, kwargs, or fallback."""
    # 1. CCXT Linear USDT Perpetual: 'APT/USDT:USDT' -> clean 'APTUSDT'
    assert extract_symbol_from_args(("APT/USDT:USDT", "market"), {}) == "APTUSDT"

    # 2. Standard Spot/Futures: 'BTC/USDT' -> 'BTCUSDT'
    assert extract_symbol_from_args(("BTC/USDT", "limit"), {}) == "BTCUSDT"

    # 3. Bare symbol: 'ETHUSDT'
    assert extract_symbol_from_args(("ETHUSDT", 10), {}) == "ETHUSDT"

    # 4. From kwargs
    assert extract_symbol_from_args((), {"symbol": "SOL/USDT:USDT"}) == "SOLUSDT"
    assert extract_symbol_from_args((), {"symbol": "DOGEUSDT"}) == "DOGEUSDT"

    # 5. Fallback when no symbol is involved (e.g. fetch_balance)
    assert extract_symbol_from_args((), {}) == "GLOBAL"
    assert extract_symbol_from_args((123, True), {"params": {}}) == "GLOBAL"


@pytest.mark.asyncio
async def test_gateway_concurrent_requests_same_symbol(temp_gateway_dir):
    """Edge: Multiple concurrent requests for the same symbol generate distinct cache files."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir, chat_id="12345")

    async def make_req(idx: int):
        ts = f"202609041200000000{idx:02d}"
        return await logger.write_request_cache("fetch_order", (idx,), {}, ts, "BTCUSDT")

    tasks = [make_req(i) for i in range(15)]
    paths = await asyncio.gather(*tasks)

    assert len(set(paths)) == 15
    assert all(os.path.exists(p) for p in paths)


# ==============================================================================
# 4. BUSINESS & LOGIC (REQ-RES CORRELATION & MULTI-GATEWAY)
# ==============================================================================
@pytest.mark.asyncio
async def test_gateway_req_res_timestamp_correlation(temp_gateway_dir):
    """Business/Logic: Exactly matched timestamp_str connects REQ and RES files 1:1."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir, chat_id="12345")
    shared_timestamp = "20260904120000999888"
    sym = "AVAXUSDT"
    method = "cancel_order"

    req_path = await logger.write_request_cache(method, (123,), {}, shared_timestamp, sym)
    res_path = await logger.write_response_cache(method, {"status": "canceled"}, shared_timestamp, sym, 50.0)

    assert req_path.replace("_REQ.json", "") == res_path.replace("_RES.json", "")
    req_data = await logger.read_request_cache(shared_timestamp, sym, method)
    res_data = await logger.read_response_cache(shared_timestamp, sym, method)

    assert req_data is not None and res_data is not None
    assert req_data["symbol"] == sym
    assert res_data["response"]["status"] == "canceled"


@pytest.mark.asyncio
async def test_gateway_custom_gateway_names_isolate_directories(temp_gateway_dir):
    """Business/Logic: Initializing with different gateway_names cleanly isolates their folders."""
    telegram_logger = GatewayCacheLogger(
        gateway_name="telegram",
        base_path=temp_gateway_dir,
        chat_id="111",
    )
    bybit_logger = GatewayCacheLogger(
        gateway_name="bybit",
        base_path=temp_gateway_dir,
        chat_id="222",
    )

    t_path = await telegram_logger.write_request_cache("send_message", (), {}, "1", "GLOBAL")
    b_path = await bybit_logger.write_request_cache("create_order", (), {}, "1", "BTCUSDT")

    assert os.path.exists(t_path)
    assert os.path.exists(b_path)
    assert "111" in t_path
    assert "222" in b_path


# ==============================================================================
# 5. SECURITY (SECRET MASKING & PATH TRAVERSAL)
# ==============================================================================
@pytest.mark.asyncio
async def test_gateway_secrets_in_args_and_kwargs_masked(temp_gateway_dir):
    """Security: Credentials and signatures in REST calls are masked before hitting disk."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir, chat_id="12345")
    timestamp_str = "20260904120000888999"

    kwargs = {
        "params": {
            "apiKey": "super_secret_api_key",
            "secret": "my_secret_token",
            "signature": "sha256_sig_12345",
        }
    }

    path = await logger.write_request_cache(
        method_name="private_post_order",
        args=(),
        kwargs=kwargs,
        timestamp_str=timestamp_str,
        symbol="GLOBAL",
    )

    saved_data = await logger.read_request_cache(timestamp_str, "GLOBAL", "private_post_order")
    assert saved_data is not None
    params = saved_data["kwargs"]["params"]
    assert params["apiKey"] == "***MASKED***"
    assert params["secret"] == "***MASKED***"
    assert params["signature"] == "***MASKED***"


@pytest.mark.asyncio
async def test_gateway_path_traversal_in_symbol_or_method(temp_gateway_dir):
    """Security: Dangerous characters in symbol or method name are stripped."""
    logger = GatewayCacheLogger(gateway_name="binance", rest_base_path=temp_gateway_dir, chat_id="12345")
    timestamp_str = "20260904120000555666"

    path = await logger.write_request_cache(
        method_name="../../etc/passwd",
        args=(),
        kwargs={},
        timestamp_str=timestamp_str,
        symbol="chat/../../BTC",
    )

    assert os.path.exists(path)
    assert "etcpasswd" in path
    assert "chatBTC" in path
    assert "../" not in path
