"""Unit tests for WebSocket log cache .tar.gz archiver and daily scheduler background job."""

import os
import tarfile
import pytest
import pytest_asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.utils.ws_cache_logger import archive_ws_cache_sync, archive_ws_cache
from src.infrastructure.scheduler import SchedulerService


@pytest.fixture
def temp_ws_cache_dir(tmp_path):
    """Create a temporary directory structure mimicking wsbinance logs."""
    base_dir = tmp_path / "wsbinance"
    chat_id = "846740826"
    cache_dir = base_dir / chat_id / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Populate cache with various files (.json, .txt, .log) - all without exception
    f1 = cache_dir / "20260828090001_101_WSLISTENER.json"
    f1.write_text('{"event": "ORDER_TRADE_UPDATE", "id": 101}', encoding="utf-8")

    f2 = cache_dir / "20260828090002_102_WSLISTENER.json"
    f2.write_text('{"event": "ORDER_TRADE_UPDATE", "id": 102}', encoding="utf-8")

    f3 = cache_dir / "raw_stream_debug.txt"
    f3.write_text("debug text log", encoding="utf-8")

    return {
        "base_dir": str(base_dir),
        "chat_id": chat_id,
        "cache_dir": str(cache_dir),
        "files": [str(f1), str(f2), str(f3)],
    }


def test_archive_ws_cache_sync_creates_tar_gz_and_cleans_cache(temp_ws_cache_dir):
    """Test that all files in cache/ are compressed to .tar.gz in backup_cache/YEAR/MONTH/DATE/ and cleaned up."""
    base_dir = temp_ws_cache_dir["base_dir"]
    chat_id = temp_ws_cache_dir["chat_id"]
    cache_dir = temp_ws_cache_dir["cache_dir"]

    ref_time = datetime(2026, 8, 28, 9, 7, 31)
    results = archive_ws_cache_sync(base_path=base_dir, now=ref_time)

    assert len(results) == 1
    res = results[0]
    assert res["chat_id"] == chat_id
    assert res["archived_count"] == 3
    assert res["deleted_count"] == 3

    # Expected path: <base_dir>/846740826/backup_cache/2026/08/28/wsbinance_2026-08-28_09-07-31.tar.gz
    expected_archive = os.path.join(
        base_dir, chat_id, "backup_cache", "2026", "08", "28", "wsbinance_2026-08-28_09-07-31.tar.gz"
    )
    assert res["archive_path"] == expected_archive
    assert os.path.exists(expected_archive)
    assert os.path.getsize(expected_archive) > 0

    # Verify tarball contents
    with tarfile.open(expected_archive, "r:gz") as tar:
        member_names = tar.getnames()
        assert "20260828090001_101_WSLISTENER.json" in member_names
        assert "20260828090002_102_WSLISTENER.json" in member_names
        assert "raw_stream_debug.txt" in member_names

        # Verify content integrity
        f1_extracted = tar.extractfile("20260828090001_101_WSLISTENER.json")
        assert f1_extracted is not None
        assert '{"event": "ORDER_TRADE_UPDATE", "id": 101}'.encode("utf-8") in f1_extracted.read()

    # Verify original cache directory is now empty
    remaining_files = os.listdir(cache_dir)
    assert len(remaining_files) == 0


@pytest.mark.asyncio
async def test_archive_ws_cache_async_wrapper(temp_ws_cache_dir):
    """Test async wrapper archive_ws_cache."""
    base_dir = temp_ws_cache_dir["base_dir"]
    ref_time = datetime(2026, 8, 28, 1, 0, 0)

    results = await archive_ws_cache(base_path=base_dir, now=ref_time)
    assert len(results) == 1
    assert results[0]["archived_count"] == 3


def test_archive_ws_cache_empty_directory_handled_gracefully(tmp_path):
    """Test that empty cache folder produces no empty tar.gz archives."""
    base_dir = tmp_path / "wsbinance_empty"
    chat_id = "12345"
    cache_dir = base_dir / chat_id / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    results = archive_ws_cache_sync(base_path=str(base_dir))
    assert len(results) == 0

    backup_dir = base_dir / chat_id / "backup_cache"
    assert not backup_dir.exists()


@pytest.mark.asyncio
async def test_scheduler_run_archive_ws_cache_job(temp_ws_cache_dir):
    """Test SchedulerService.run_archive_ws_cache_job execution."""
    base_dir = temp_ws_cache_dir["base_dir"]

    scheduler = SchedulerService(
        daily_risk_repo=MagicMock(),
        trading_account_repo=MagicMock(),
        risk_profile_repo=MagicMock(),
        trade_repo=MagicMock(),
        order_repo=MagicMock(),
        instrument_repo=MagicMock(),
        trade_summary_repo=MagicMock(),
        trade_event_repo=MagicMock(),
        bot_log_repo=MagicMock(),
        bot_setting_repo=MagicMock(),
    )

    results = await scheduler.run_archive_ws_cache_job(base_path=base_dir)
    assert len(results) == 1
    assert results[0]["archived_count"] == 3


@pytest.mark.asyncio
async def test_scheduler_service_job_registration():
    """Verify that start() registers all 8 maintenance jobs including archive_ws_cache."""
    scheduler = SchedulerService(
        daily_risk_repo=MagicMock(),
        trading_account_repo=MagicMock(),
        risk_profile_repo=MagicMock(),
        trade_repo=MagicMock(),
        order_repo=MagicMock(),
        instrument_repo=MagicMock(),
        trade_summary_repo=MagicMock(),
        trade_event_repo=MagicMock(),
        bot_log_repo=MagicMock(),
        bot_setting_repo=MagicMock(),
    )

    scheduler.start()
    job_ids = [j.id for j in scheduler.scheduler.get_jobs()]
    scheduler.stop()

    assert "archive_ws_cache" in job_ids
    assert "daily_risk_snapshot" in job_ids
    assert "cleanup_orphan_orders" in job_ids
    assert "failsafe_sync_check" in job_ids
    assert "sync_instruments_metadata" in job_ids
    assert "purge_old_logs" in job_ids
    assert "daily_performance_report" in job_ids
    assert "heartbeat_health_check" in job_ids
    assert len(job_ids) == 8
