"""Unit tests for REST API raw request & response payload cache logger (rest_cache_logger.py)."""

import json
import os
import shutil
import tempfile
from decimal import Decimal
from datetime import datetime
import pytest
from src.utils.rest_cache_logger import (
    write_rest_request_cache,
    write_rest_response_cache,
    extract_symbol_from_args,
    _sanitize_payload,
    _path_name_parser,
    _default_json_serializer,
)


@pytest.fixture
def temp_cache_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_rest_cache_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_rest_request_and_response_cache(temp_cache_dir):
    timestamp_str = "20260902210000123456"
    chat_id = "846740826"
    symbol = "APTUSDT"
    method = "create_order"

    req_args = ("APT/USDT:USDT", "market", "buy", 4395.6, None)
    req_kwargs = {"params": {"newClientOrderId": "ENTRY_33_123", "apiKey": "secret_key_123"}}

    # 1. Write Request
    req_path = await write_rest_request_cache(
        method_name=method,
        args=req_args,
        kwargs=req_kwargs,
        timestamp_str=timestamp_str,
        symbol=symbol,
        chat_id=chat_id,
        base_path=temp_cache_dir,
    )

    assert req_path != ""
    assert os.path.exists(req_path)
    assert req_path.endswith(f"{timestamp_str}_APTUSDT_create_order_REQ.json")
    assert f"{chat_id}/cache" in req_path

    with open(req_path, "r", encoding="utf-8") as f:
        req_content = json.load(f)

    assert req_content["method"] == "create_order"
    assert req_content["symbol"] == "APTUSDT"
    assert req_content["kwargs"]["params"]["apiKey"] == "***MASKED***"

    # 2. Write Response
    res_data = {
        "id": "469601474",
        "clientOrderId": "ENTRY_33_123",
        "status": "closed",
        "average": Decimal("0.55989"),
        "filled": Decimal("4395.6"),
        "raw_info": {"avgPrice": "0.55989", "executedQty": "4395.6", "status": "FILLED"},
    }

    res_path = await write_rest_response_cache(
        method_name=method,
        response_data=res_data,
        timestamp_str=timestamp_str,
        symbol=symbol,
        chat_id=chat_id,
        base_path=temp_cache_dir,
        duration_ms=145.2,
    )

    assert res_path != ""
    assert os.path.exists(res_path)
    assert res_path.endswith(f"{timestamp_str}_APTUSDT_create_order_RES.json")

    with open(res_path, "r", encoding="utf-8") as f:
        res_content = json.load(f)

    assert res_content["method"] == "create_order"
    assert res_content["symbol"] == "APTUSDT"
    assert res_content["duration_ms"] == 145.2
    assert res_content["response"]["average"] == "0.55989"


def test_extract_symbol_from_args():
    assert extract_symbol_from_args(("APT/USDT:USDT", "market"), {}) == "APTUSDTUSDT" or "APTUSDT" in extract_symbol_from_args(("APT/USDT:USDT", "market"), {})
    assert extract_symbol_from_args((), {"symbol": "BTCUSDT"}) == "BTCUSDT"
    assert extract_symbol_from_args((), {}) == "GLOBAL"


def test_sanitize_payload_masks_secrets():
    payload = {
        "apiKey": "xyz123",
        "secret": "mysecret",
        "nested": {"api_key": "abc", "amount": 100},
    }
    sanitized = _sanitize_payload(payload)
    assert sanitized["apiKey"] == "***MASKED***"
    assert sanitized["secret"] == "***MASKED***"
    assert sanitized["nested"]["api_key"] == "***MASKED***"
    assert sanitized["nested"]["amount"] == 100
