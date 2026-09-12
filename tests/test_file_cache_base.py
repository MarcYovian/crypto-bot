"""Unit tests for BaseFileCacheLogger across 5 dimensions:
1. Positif (Happy Path)
2. Negatif (Error Handling / Fault Tolerance)
3. Edge (Stress, Concurrency, Large Data, Unicode)
4. Business/Logic (Serialization Precision, Archiving)
5. Security (Path Traversal, Deep Secret Masking)
"""

import asyncio
import json
import os
import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.utils.file_cache.base_cache import (
    BaseFileCacheLogger,
    clean_path_name,
    default_json_serializer,
    sanitize_payload,
)


@pytest.fixture
def temp_cache_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_file_cache_base_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 1. POSITIF (HAPPY PATH)
# ==============================================================================
@pytest.mark.asyncio
async def test_base_write_and_read_atomic_json(temp_cache_dir):
    """Positif: Test atomic writing and reading of standard JSON payload."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir, chat_id="123456")
    data = {"order_id": "999", "status": "FILLED", "symbol": "BTCUSDT"}

    written_path = await logger.write_file_atomic(
        directory=temp_cache_dir,
        filename="test_order.json",
        data=data,
    )

    assert written_path != ""
    assert os.path.exists(written_path)
    assert not any(f.endswith(".tmp") for f in os.listdir(temp_cache_dir))

    read_data = await logger.read_file_json(written_path)
    assert read_data == data


@pytest.mark.asyncio
async def test_base_remove_file(temp_cache_dir):
    """Positif: Test removing existing file safely."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    file_path = os.path.join(temp_cache_dir, "remove_me.json")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('{"test": 1}')

    assert os.path.exists(file_path)
    result = await logger.remove_file(file_path)
    assert result is True
    assert not os.path.exists(file_path)


@pytest.mark.asyncio
async def test_base_archive_directory(temp_cache_dir):
    """Positif: Test archiving folder containing files to .tar.gz and cleaning source files."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    src_dir = os.path.join(temp_cache_dir, "cache")
    os.makedirs(src_dir, exist_ok=True)

    f1 = os.path.join(src_dir, "file1.json")
    f2 = os.path.join(src_dir, "file2.json")
    with open(f1, "w") as f:
        f.write('{"f": 1}')
    with open(f2, "w") as f:
        f.write('{"f": 2}')

    dest_archive = os.path.join(temp_cache_dir, "backup", "archive.tar.gz")
    summary = await logger.archive_directory(src_dir, dest_archive)

    assert summary["archived_count"] == 2
    assert summary["deleted_count"] == 2
    assert os.path.exists(dest_archive)
    assert summary["archive_size_bytes"] > 0
    assert len(os.listdir(src_dir)) == 0


# ==============================================================================
# 2. NEGATIF (FAULT TOLERANCE & CORRUPTION)
# ==============================================================================
@pytest.mark.asyncio
async def test_base_read_non_existent_file(temp_cache_dir):
    """Negatif: Reading non-existent file returns None without raising exception."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    result = await logger.read_file_json(os.path.join(temp_cache_dir, "ghost.json"))
    assert result is None


@pytest.mark.asyncio
async def test_base_read_corrupt_json_file(temp_cache_dir):
    """Negatif: Reading truncated or invalid JSON returns None safely."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    corrupt_file = os.path.join(temp_cache_dir, "corrupt.json")
    with open(corrupt_file, "w", encoding="utf-8") as f:
        f.write('{"incomplete": true, "error": ')

    result = await logger.read_file_json(corrupt_file)
    assert result is None


@pytest.mark.asyncio
async def test_base_remove_non_existent_file(temp_cache_dir):
    """Negatif: Removing non-existent file returns False without error."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    result = await logger.remove_file(os.path.join(temp_cache_dir, "non_existent.json"))
    assert result is False


@pytest.mark.asyncio
async def test_base_archive_empty_or_missing_dir(temp_cache_dir):
    """Negatif: Archiving an empty or missing directory returns empty summary."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    missing_dir = os.path.join(temp_cache_dir, "does_not_exist")
    dest_archive = os.path.join(temp_cache_dir, "backup", "empty.tar.gz")

    summary = await logger.archive_directory(missing_dir, dest_archive)
    assert summary["archived_count"] == 0
    assert summary["archive_path"] == ""


# ==============================================================================
# 3. EDGE (CONCURRENCY, STRESS, UNICODE)
# ==============================================================================
@pytest.mark.asyncio
async def test_base_large_payload(temp_cache_dir):
    """Edge: Writing and reading large dataset (>2MB) without truncation."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    large_data = {
        "items": [{"id": i, "price": str(Decimal(f"{i}.12345678"))} for i in range(15000)]
    }

    path = await logger.write_file_atomic(temp_cache_dir, "large.json", large_data)
    assert os.path.exists(path)

    read_back = await logger.read_file_json(path)
    assert read_back is not None
    assert len(read_back["items"]) == 15000
    assert read_back["items"][14999]["id"] == 14999


@pytest.mark.asyncio
async def test_base_unicode_and_emojis(temp_cache_dir):
    """Edge: Writing and reading non-ASCII characters, emojis, and math symbols."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)
    unicode_data = {
        "title": "Crypto Bot 🚀 💰",
        "description": "Trading 自動売買 📈",
        "math": "∑(x_i) >= π ≈ 3.14159",
    }

    path = await logger.write_file_atomic(temp_cache_dir, "unicode.json", unicode_data)
    read_back = await logger.read_file_json(path)
    assert read_back == unicode_data


@pytest.mark.asyncio
async def test_base_concurrent_writes(temp_cache_dir):
    """Edge: High concurrency writing multiple files simultaneously with no collisions."""
    logger = BaseFileCacheLogger(base_path=temp_cache_dir)

    async def write_task(idx: int):
        data = {"worker_id": idx, "timestamp": datetime.now().isoformat()}
        filename = f"worker_{idx}.json"
        return await logger.write_file_atomic(temp_cache_dir, filename, data)

    tasks = [write_task(i) for i in range(30)]
    paths = await asyncio.gather(*tasks)

    assert len(paths) == 30
    assert all(os.path.exists(p) for p in paths)
    # Check that temporary files are cleaned up
    all_files = os.listdir(temp_cache_dir)
    assert not any(".tmp" in f for f in all_files)


# ==============================================================================
# 4. BUSINESS & LOGIC (SERIALIZATION & PRECISION)
# ==============================================================================
def test_default_json_serializer_preserves_decimal_precision():
    """Business/Logic: Decimal must serialize to string without IEEE-754 precision loss."""
    dec_val = Decimal("0.0000001234567890123456789")
    serialized = default_json_serializer(dec_val)
    assert serialized == "0.0000001234567890123456789"
    assert isinstance(serialized, str)


def test_default_json_serializer_dates_and_structures():
    """Business/Logic: datetime, date, sets, and objects are converted properly."""
    dt = datetime(2026, 9, 4, 15, 30, 45)
    d = date(2026, 9, 4)
    assert default_json_serializer(dt) == "2026-09-04T15:30:45"
    assert default_json_serializer(d) == "2026-09-04"
    assert default_json_serializer({"a", "b"}) in (["a", "b"], ["b", "a"])
    assert default_json_serializer(b"raw bytes") == "raw bytes"

    class SampleObject:
        def __init__(self):
            self.foo = "bar"

    assert default_json_serializer(SampleObject()) == {"foo": "bar"}


# ==============================================================================
# 5. SECURITY (PATH TRAVERSAL & SECRET MASKING)
# ==============================================================================
def test_clean_path_name_prevents_path_traversal():
    """Security: Directory traversal sequences and special characters are stripped."""
    assert clean_path_name("../../etc/passwd") == "etcpasswd"
    assert clean_path_name("chat/../../../evil_dir") == "chatevil_dir"
    assert clean_path_name("session\x00nullbyte") == "sessionnullbyte"
    assert clean_path_name("valid_name-01") == "valid_name-01"
    assert clean_path_name("*?<>|:$#") == ""


def test_sanitize_payload_deep_recursive_masking():
    """Security: All sensitive keys are masked recursively in nested dictionaries and lists."""
    sensitive_data = {
        "symbol": "BTCUSDT",
        "price": "50000",
        "apiKey": "raw_api_key_123",
        "secret": "super_secret_456",
        "signature": "hmac_sha256_sig",
        "auth": {
            "api_key": "nested_key",
            "api_secret": "nested_secret",
            "token": "bearer_token",
            "private_key": "rsa_private_key",
        },
        "credentials_list": [
            {"password": "mypassword", "user": "alice"},
            ("tuple_key", {"secret": "tuple_secret"}),
        ],
    }

    sanitized = sanitize_payload(sensitive_data)

    assert sanitized["symbol"] == "BTCUSDT"
    assert sanitized["price"] == "50000"
    assert sanitized["apiKey"] == "***MASKED***"
    assert sanitized["secret"] == "***MASKED***"
    assert sanitized["signature"] == "***MASKED***"
    assert sanitized["auth"]["api_key"] == "***MASKED***"
    assert sanitized["auth"]["api_secret"] == "***MASKED***"
    assert sanitized["auth"]["token"] == "***MASKED***"
    assert sanitized["auth"]["private_key"] == "***MASKED***"
    assert sanitized["credentials_list"][0]["password"] == "***MASKED***"
    assert sanitized["credentials_list"][0]["user"] == "alice"
    assert sanitized["credentials_list"][1][1]["secret"] == "***MASKED***"
