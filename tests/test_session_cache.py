"""Unit tests for SessionCacheLogger across 5 dimensions:
1. Positif (Happy Path)
2. Negatif (Error Handling / Fault Tolerance)
3. Edge (TTL Boundary Conditions, Zero/None TTL, Concurrency)
4. Business/Logic (Auto-Cleanup on Expiry, Session Type Partitioning)
5. Security (Session ID Path Traversal, Sensitive Data Masking)
"""

import asyncio
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta

import pytest

from src.utils.file_cache.session_cache import SessionCacheLogger


@pytest.fixture
def temp_session_dir():
    temp_dir = tempfile.mkdtemp(prefix="test_session_cache_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 1. POSITIF (HAPPY PATH)
# ==============================================================================
@pytest.mark.asyncio
async def test_session_write_and_read_active(temp_session_dir):
    """Positif: Write active session with TTL and read it back successfully."""
    logger = SessionCacheLogger(
        session_type="user_session",
        base_path=temp_session_dir,
        chat_id="12345",
        default_ttl_seconds=3600,
    )

    data = {"user_id": 42, "role": "trader", "state": "WAITING_SIGNAL"}
    path = await logger.write_session("session_42", data, ttl_seconds=3600)

    assert os.path.exists(path)
    assert path.endswith("session_42.json")

    read_back = await logger.read_session("session_42")
    assert read_back is not None
    assert read_back["user_id"] == 42
    assert read_back["role"] == "trader"
    assert read_back["state"] == "WAITING_SIGNAL"


@pytest.mark.asyncio
async def test_session_remove(temp_session_dir):
    """Positif: Remove an active session file successfully."""
    logger = SessionCacheLogger(
        session_type="user_session",
        base_path=temp_session_dir,
        chat_id="12345",
    )

    await logger.write_session("to_delete", {"val": 1})
    read_before = await logger.read_session("to_delete")
    assert read_before is not None

    removed = await logger.remove_session("to_delete")
    assert removed is True

    read_after = await logger.read_session("to_delete")
    assert read_after is None


# ==============================================================================
# 2. NEGATIF (ERROR HANDLING & FAULT TOLERANCE)
# ==============================================================================
@pytest.mark.asyncio
async def test_session_read_non_existent(temp_session_dir):
    """Negatif: Reading non-existent session returns None without exception."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")
    assert await logger.read_session("ghost_session") is None


@pytest.mark.asyncio
async def test_session_read_corrupt_file(temp_session_dir):
    """Negatif: Reading corrupted session file returns None safely."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")
    corrupt_path = os.path.join(logger.session_dir, "corrupt_sid.json")
    os.makedirs(logger.session_dir, exist_ok=True)
    with open(corrupt_path, "w") as f:
        f.write('{"invalid_json": ')

    result = await logger.read_session("corrupt_sid")
    assert result is None


@pytest.mark.asyncio
async def test_session_write_empty_id(temp_session_dir):
    """Negatif: Writing session with empty or purely illegal characters returns empty string."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")
    assert await logger.write_session("", {"a": 1}) == ""
    assert await logger.write_session("*?<>", {"a": 1}) == ""


# ==============================================================================
# 3. EDGE (TTL BOUNDARIES, ZERO/NONE TTL, CONCURRENCY)
# ==============================================================================
@pytest.mark.asyncio
async def test_session_zero_ttl_immediately_expired(temp_session_dir):
    """Edge: Session created with ttl=0 is immediately marked expired."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")

    await logger.write_session("zero_ttl", {"action": "panic"}, ttl_seconds=0)
    result = await logger.read_session("zero_ttl")
    assert result is None


@pytest.mark.asyncio
async def test_session_permanent_none_ttl(temp_session_dir):
    """Edge: Session with default_ttl_seconds <= 0 / expired_at=None never expires."""
    logger = SessionCacheLogger(
        base_path=temp_session_dir,
        chat_id="12345",
        default_ttl_seconds=0,
    )

    file_path = os.path.join(logger.session_dir, "permanent.json")
    os.makedirs(logger.session_dir, exist_ok=True)

    # Payload with no expired_at
    payload = {
        "session_id": "permanent",
        "expired_at": None,
        "data": {"permanent_key": "val"},
    }
    await logger.write_file_atomic(logger.session_dir, "permanent.json", payload)

    read_back = await logger.read_session("permanent")
    assert read_back is not None
    assert read_back["permanent_key"] == "val"


@pytest.mark.asyncio
async def test_session_boundary_expiry_timing(temp_session_dir):
    """Edge: Validate precision of expiration boundary check."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")

    # 1. Expired 1 second ago
    past_time = (datetime.now() - timedelta(seconds=1)).isoformat()
    past_payload = {
        "session_id": "expired_test",
        "expired_at": past_time,
        "data": {"state": "dead"},
    }
    assert logger.is_expired(past_payload) is True

    # 2. Expires 5 seconds from now
    future_time = (datetime.now() + timedelta(seconds=5)).isoformat()
    future_payload = {
        "session_id": "active_test",
        "expired_at": future_time,
        "data": {"state": "alive"},
    }
    assert logger.is_expired(future_payload) is False


@pytest.mark.asyncio
async def test_session_concurrent_writes(temp_session_dir):
    """Edge: Concurrent writes of multiple session files."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")

    async def write_user_session(uid: int):
        return await logger.write_session(f"user_{uid}", {"uid": uid, "login_at": time.time()})

    tasks = [write_user_session(i) for i in range(20)]
    paths = await asyncio.gather(*tasks)

    assert len(set(paths)) == 20
    assert all(os.path.exists(p) for p in paths)


# ==============================================================================
# 4. BUSINESS & LOGIC (AUTO-CLEANUP & DIRECTORY PARTITIONING)
# ==============================================================================
@pytest.mark.asyncio
async def test_session_auto_cleanup_on_read(temp_session_dir):
    """Business/Logic: Expired session file is automatically deleted when read with auto_cleanup=True."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")
    await logger.write_session("stale_session", {"temp": True}, ttl_seconds=0)

    stale_file = os.path.join(logger.session_dir, "stale_session.json")
    assert os.path.exists(stale_file)

    # Reading with auto_cleanup deletes the stale file
    res = await logger.read_session("stale_session", auto_cleanup=True)
    assert res is None
    assert not os.path.exists(stale_file)


@pytest.mark.asyncio
async def test_session_no_auto_cleanup(temp_session_dir):
    """Business/Logic: Expired session is NOT deleted when auto_cleanup=False."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")
    await logger.write_session("preserve_stale", {"temp": True}, ttl_seconds=0)

    stale_file = os.path.join(logger.session_dir, "preserve_stale.json")
    assert os.path.exists(stale_file)

    res = await logger.read_session("preserve_stale", auto_cleanup=False)
    assert res is None
    assert os.path.exists(stale_file)


@pytest.mark.asyncio
async def test_session_type_directory_partitioning(temp_session_dir):
    """Business/Logic: Different session_type instances partition cleanly into separate directories."""
    auth_logger = SessionCacheLogger(session_type="auth_token", base_path=temp_session_dir, chat_id="123")
    conv_logger = SessionCacheLogger(session_type="conversation", base_path=temp_session_dir, chat_id="123")

    p1 = await auth_logger.write_session("token1", {"t": 1})
    p2 = await conv_logger.write_session("token1", {"c": 2})

    assert "auth_token" in p1
    assert "conversation" in p2
    assert p1 != p2


# ==============================================================================
# 5. SECURITY (PATH TRAVERSAL & SENSITIVE DATA MASKING)
# ==============================================================================
@pytest.mark.asyncio
async def test_session_path_traversal_session_id(temp_session_dir):
    """Security: Directory traversal in session_id is safely sanitized."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")

    path = await logger.write_session("../../evil_session_id", {"exploit": False})
    assert os.path.exists(path)
    assert "evil_session_id" in path
    assert "../" not in path


@pytest.mark.asyncio
async def test_session_sensitive_data_in_session_masked(temp_session_dir):
    """Security: Sensitive fields inside session payload are masked by default."""
    logger = SessionCacheLogger(base_path=temp_session_dir, chat_id="12345")

    data = {
        "user": "bob",
        "password": "plain_password_123",
        "token": "secret_jwt_token",
    }

    await logger.write_session("sec_session", data)
    raw_file = await logger.read_file_json(os.path.join(logger.session_dir, "sec_session.json"))

    assert raw_file["data"]["user"] == "bob"
    assert raw_file["data"]["password"] == "***MASKED***"
    assert raw_file["data"]["token"] == "***MASKED***"
