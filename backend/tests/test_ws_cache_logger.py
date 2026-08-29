"""Unit tests for WebSocket order event raw payload cache logger (ws_cache_logger.py)."""

import json
import os
import shutil
import tempfile
from datetime import datetime
from decimal import Decimal
import pytest
from src.utils.ws_cache_logger import (
    write_ws_order_cache,
    _path_name_parser,
    _default_json_serializer,
)


@pytest.fixture
def temp_cache_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_ws_cache_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_ws_order_cache_success(temp_cache_dir):
    order_data = {
        "id": "421667175",
        "clientOrderId": "ENTRY_18_1787842178441",
        "symbol": "VETUSDT",
        "side": "BUY",
        "status": "FILLED",
        "price": Decimal("0.007141"),
        "filled": Decimal("993192.0"),
        "timestamp": datetime.now(),
        "info": {
            "o": "MARKET",
            "R": False,
            "rp": "0.00000000",
        },
    }

    chat_id = "846740826"
    written_path = await write_ws_order_cache(
        order_data=order_data,
        chat_id=chat_id,
        base_path=temp_cache_dir,
    )

    assert written_path != ""
    assert os.path.exists(written_path)
    assert written_path.endswith("_WSLISTENER.json")
    assert "846740826" in written_path
    assert "cache" in written_path

    # Verify JSON content
    with open(written_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    assert content["chat_id"] == "846740826"
    assert content["tag"] == "WSLISTENER"
    assert content["data"]["id"] == "421667175"
    assert content["data"]["status"] == "FILLED"
    assert content["data"]["price"] == "0.007141"


@pytest.mark.asyncio
async def test_write_ws_order_cache_empty_or_none(temp_cache_dir):
    result_none = await write_ws_order_cache(None, base_path=temp_cache_dir)
    assert result_none == ""

    result_empty = await write_ws_order_cache({}, base_path=temp_cache_dir)
    assert result_empty == ""


def test_path_name_parser():
    assert _path_name_parser("846740826") == "846740826"
    assert _path_name_parser("chat/123:456?*") == "chat123456"
    assert _path_name_parser("user_name-01") == "user_name-01"


def test_default_json_serializer():
    assert _default_json_serializer(Decimal("123.45")) == "123.45"
    dt = datetime(2026, 8, 27, 22, 30, 0)
    assert _default_json_serializer(dt) == "2026-08-27T22:30:00"
    assert _default_json_serializer({"a", "b"}) in (["a", "b"], ["b", "a"])
