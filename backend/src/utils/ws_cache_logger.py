"""WebSocket order event raw payload cache logger.

Inspired by session.py atomic file write & structured caching pattern.
Stores raw incoming Binance WebSocket event data to:
/var/log/cryptobot/wsbinance/<TELEGRAM_CHAT_ID>/cache/<timestamp>_WSLISTENER.json
"""

import asyncio
import json
import logging
import os
import random
import re
import tarfile
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional, Union, List, Dict

from config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_PATH = getattr(settings, "WS_CACHE_LOG_PATH", "/var/log/cryptobot/wsbinance/")


def _path_name_parser(data: str) -> str:
    """Sanitize path name to avoid invalid characters."""
    regex = re.compile(r"[^a-zA-Z0-9_\-]")
    return regex.sub("", str(data))


def _default_json_serializer(obj: Any) -> Any:
    """Safely serialize non-standard JSON types like Decimal, datetime, etc."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _sync_atomic_write_cache(target_dir: str, filename: str, payload_str: str) -> str:
    """Synchronous worker that performs atomic write via temp file rename."""
    try:
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        rand_id = str(random.randint(1000, 9999))
        temp_path = f"{target_path}.tmp_{os.getpid()}_{rand_id}"

        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload_str)

        os.rename(temp_path, target_path)
        return target_path
    except Exception as e:
        logger.warning(f"Failed atomic writing WebSocket cache to {target_dir}/{filename}: {e}")
        return ""


async def write_ws_order_cache(
    order_data: Any,
    chat_id: Optional[Union[int, str]] = None,
    base_path: Optional[str] = None,
    tag: str = "WSLISTENER",
) -> str:
    """Asynchronously record raw Binance WebSocket order payload to JSON cache file.

    Path format:
        {base_path}/{chat_id}/cache/{timestamp}_{order_id}_{tag}.json

    Args:
        order_data: Raw or parsed WebSocket event dict payload.
        chat_id: Telegram Chat ID (defaults to settings.TELEGRAM_CHAT_ID).
        base_path: Root folder for cache (defaults to settings.WS_CACHE_LOG_PATH).
        tag: Filename suffix identifier (default: "WSLISTENER").

    Returns:
        Absolute filepath string if successfully written, or empty string on failure.
    """
    if not order_data:
        return ""

    try:
        root_path = base_path or getattr(settings, "WS_CACHE_LOG_PATH", "/var/log/cryptobot/wsbinance/")
        resolved_chat_id = chat_id or getattr(settings, "TELEGRAM_CHAT_ID", "846740826") or "default"
        clean_chat_id = _path_name_parser(str(resolved_chat_id))

        target_dir = os.path.join(root_path, clean_chat_id, "cache")
        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d%H%M%S%f")

        order_id = ""
        if isinstance(order_data, dict):
            raw_id = order_data.get("id") or order_data.get("orderId") or ""
            if raw_id:
                order_id = f"_{_path_name_parser(str(raw_id))}"

        filename = f"{timestamp_str}{order_id}_{tag}.json"

        # Structure standardized cache wrapper
        cache_entry = {
            "logged_at": now.isoformat(),
            "chat_id": str(resolved_chat_id),
            "tag": tag,
            "data": order_data,
        }

        payload_str = json.dumps(cache_entry, default=_default_json_serializer, indent=2)

        # Offload file I/O to background thread to avoid blocking asyncio event loop
        written_path = await asyncio.to_thread(_sync_atomic_write_cache, target_dir, filename, payload_str)
        return written_path
    except Exception as e:
        logger.warning(f"Error preparing WS cache log: {e}")
        return ""


def archive_ws_cache_sync(
    base_path: Optional[str] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Synchronously archive all files in cache/ directories into .tar.gz backups.

    Structure:
        Source: {base_path}/{chat_id}/cache/* (all files without exception)
        Dest:   {base_path}/{chat_id}/backup_cache/{YEAR}/{MONTH}/{DATE}/wsbinance_{YYYY-MM-DD_HH-MM-SS}.tar.gz

    Example:
        wsbinance/846740826/backup_cache/2026/08/28/wsbinance_2026-08-28_09-07-31.tar.gz

    Args:
        base_path: Root folder for wsbinance logs (defaults to settings.WS_CACHE_LOG_PATH).
        now: Timestamp reference for archive naming (defaults to datetime.now()).

    Returns:
        List of result summaries per chat_id.
    """
    root_path = base_path or getattr(settings, "WS_CACHE_LOG_PATH", "/var/log/cryptobot/wsbinance/")
    if not os.path.exists(root_path):
        return []

    curr_time = now or datetime.now()
    year_str = curr_time.strftime("%Y")
    month_str = curr_time.strftime("%m")
    day_str = curr_time.strftime("%d")
    date_time_str = curr_time.strftime("%Y-%m-%d_%H-%M-%S")
    archive_filename = f"wsbinance_{date_time_str}.tar.gz"

    results: List[Dict[str, Any]] = []

    try:
        chat_dirs = [d for d in os.listdir(root_path) if os.path.isdir(os.path.join(root_path, d))]
    except Exception as e:
        logger.warning(f"Failed to list directories in {root_path}: {e}")
        return []

    for chat_id in chat_dirs:
        cache_dir = os.path.join(root_path, chat_id, "cache")
        if not os.path.exists(cache_dir) or not os.path.isdir(cache_dir):
            continue

        # Get all files inside cache_dir (without exception)
        try:
            entries = os.listdir(cache_dir)
            file_paths = [
                os.path.join(cache_dir, f)
                for f in entries
                if os.path.isfile(os.path.join(cache_dir, f))
            ]
        except Exception as e:
            logger.warning(f"Failed to scan cache directory {cache_dir}: {e}")
            continue

        if not file_paths:
            continue

        # Destination directory: backup_cache/<YEAR>/<MONTH>/<DATE>/
        dest_dir = os.path.join(root_path, chat_id, "backup_cache", year_str, month_str, day_str)
        os.makedirs(dest_dir, exist_ok=True)
        dest_archive_path = os.path.join(dest_dir, archive_filename)

        # Compress into .tar.gz
        try:
            with tarfile.open(dest_archive_path, "w:gz") as tar:
                for fpath in file_paths:
                    tar.add(fpath, arcname=os.path.basename(fpath))

            archive_size = os.path.getsize(dest_archive_path)

            # Safely remove original files from cache/ after successful compression
            deleted_count = 0
            for fpath in file_paths:
                try:
                    os.remove(fpath)
                    deleted_count += 1
                except Exception as del_err:
                    logger.warning(f"Could not remove archived file {fpath}: {del_err}")

            summary = {
                "chat_id": chat_id,
                "archived_count": len(file_paths),
                "deleted_count": deleted_count,
                "archive_path": dest_archive_path,
                "archive_size_bytes": archive_size,
            }
            results.append(summary)
            logger.info(
                f"Archived {len(file_paths)} files for chat_id={chat_id} into {dest_archive_path} ({archive_size} bytes)."
            )
        except Exception as arch_err:
            logger.error(f"Failed creating archive {dest_archive_path}: {arch_err}")

    return results


async def archive_ws_cache(
    base_path: Optional[str] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Asynchronously execute the cache archiver in a background thread."""
    return await asyncio.to_thread(archive_ws_cache_sync, base_path, now)
