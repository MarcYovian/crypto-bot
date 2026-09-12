"""Base file cache logger providing atomic file operations, serialization, and archiving.

Inspired by Odoo session.py atomic file write and structured caching pattern,
modernized for asynchronous Python event loops with thread offloading.
"""

import asyncio
import json
import logging
import os
import random
import re
import tarfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from config.settings import settings

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = (
    "secret",
    "apikey",
    "api_key",
    "signature",
    "password",
    "token",
    "private_key",
    "api_secret",
    "apisecret",
)


def clean_path_name(data: str) -> str:
    """Sanitize path name to avoid invalid characters and prevent path traversal."""
    if not data:
        return ""
    # Strip null bytes and any character not in [a-zA-Z0-9_\-]
    cleaned = str(data).replace("\x00", "")
    regex = re.compile(r"[^a-zA-Z0-9_\-]")
    return regex.sub("", cleaned)


def default_json_serializer(obj: Any) -> Any:
    """Safely serialize non-standard JSON types like Decimal, datetime, set, etc."""
    if isinstance(obj, Decimal):
        return f"{obj:f}"
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def sanitize_payload(obj: Any) -> Any:
    """Recursively mask sensitive keys like apiKey, secret, signature, token in payloads."""
    if isinstance(obj, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_KEYS):
                sanitized[k] = "***MASKED***"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    elif isinstance(obj, tuple):
        return [sanitize_payload(item) for item in obj]
    return obj


def _sync_atomic_write(target_dir: str, filename: str, payload_str: str) -> str:
    """Synchronous worker that performs atomic write via temp file rename."""
    try:
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        rand_id = str(random.randint(100000, 999999))
        temp_path = f"{target_path}.tmp_{os.getpid()}_{rand_id}"

        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload_str)

        os.rename(temp_path, target_path)
        try:
            os.chmod(target_path, 0o666)
        except Exception:
            pass
        return target_path
    except Exception as e:
        logger.warning(f"Failed atomic writing cache to {target_dir}/{filename}: {e}")
        return ""


def _sync_read_json(file_path: str) -> Optional[Dict[str, Any]]:
    """Synchronous worker to read and parse JSON file from disk safely."""
    try:
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content:
            return None
        return json.loads(content)
    except json.JSONDecodeError as jde:
        logger.warning(f"Corrupt JSON detected in cache file {file_path}: {jde}")
        return None
    except Exception as e:
        logger.warning(f"Failed reading cache file {file_path}: {e}")
        return None


def _sync_remove_file(file_path: str) -> bool:
    """Synchronous worker to remove file safely."""
    try:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed removing cache file {file_path}: {e}")
        return False


def _sync_archive_directory(source_dir: str, dest_archive_path: str) -> Dict[str, Any]:
    """Synchronous worker to compress all files in source_dir to .tar.gz and delete source files."""
    if not os.path.exists(source_dir) or not os.path.isdir(source_dir):
        return {
            "archived_count": 0,
            "deleted_count": 0,
            "archive_path": "",
            "archive_size_bytes": 0,
        }

    try:
        entries = os.listdir(source_dir)
        file_paths = [
            os.path.join(source_dir, f)
            for f in entries
            if os.path.isfile(os.path.join(source_dir, f))
        ]
    except Exception as e:
        logger.warning(f"Failed listing files in {source_dir}: {e}")
        return {
            "archived_count": 0,
            "deleted_count": 0,
            "archive_path": "",
            "archive_size_bytes": 0,
        }

    if not file_paths:
        return {
            "archived_count": 0,
            "deleted_count": 0,
            "archive_path": "",
            "archive_size_bytes": 0,
        }

    dest_dir = os.path.dirname(dest_archive_path)
    os.makedirs(dest_dir, exist_ok=True)

    try:
        with tarfile.open(dest_archive_path, "w:gz") as tar:
            for fpath in file_paths:
                tar.add(fpath, arcname=os.path.basename(fpath))

        archive_size = os.path.getsize(dest_archive_path)

        deleted_count = 0
        for fpath in file_paths:
            try:
                os.remove(fpath)
                deleted_count += 1
            except Exception as del_err:
                logger.warning(f"Could not remove archived file {fpath}: {del_err}")

        return {
            "archived_count": len(file_paths),
            "deleted_count": deleted_count,
            "archive_path": dest_archive_path,
            "archive_size_bytes": archive_size,
        }
    except Exception as arch_err:
        logger.error(f"Failed creating archive {dest_archive_path}: {arch_err}")
        return {
            "archived_count": 0,
            "deleted_count": 0,
            "archive_path": "",
            "archive_size_bytes": 0,
        }


class BaseFileCacheLogger:
    """Base class providing non-blocking atomic file caching and archiving capabilities."""

    def __init__(
        self,
        base_path: Optional[str] = None,
        chat_id: Optional[Union[int, str]] = None,
    ) -> None:
        raw_chat_id = chat_id or getattr(settings, "TELEGRAM_CHAT_ID", None) or "default"
        self.chat_id = clean_path_name(str(raw_chat_id)) or "default"
        self.base_path = base_path or "/var/log/cryptobot/"

    async def write_file_atomic(
        self,
        directory: str,
        filename: str,
        data: Any,
        sanitize: bool = True,
        indent: int = 2,
    ) -> str:
        """Serialize data to JSON and atomically write to disk in a background thread."""
        try:
            payload_data = sanitize_payload(data) if sanitize else data
            payload_str = json.dumps(
                payload_data,
                default=default_json_serializer,
                indent=indent,
            )
            return await asyncio.to_thread(
                _sync_atomic_write, directory, filename, payload_str
            )
        except Exception as e:
            logger.warning(f"Error preparing cache write: {e}")
            return ""

    async def read_file_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Read and parse JSON from disk in a background thread."""
        return await asyncio.to_thread(_sync_read_json, file_path)

    async def remove_file(self, file_path: str) -> bool:
        """Remove file from disk in a background thread."""
        return await asyncio.to_thread(_sync_remove_file, file_path)

    async def archive_directory(
        self,
        source_dir: str,
        dest_archive_path: str,
    ) -> Dict[str, Any]:
        """Compress directory contents to .tar.gz and purge source files in background thread."""
        return await asyncio.to_thread(
            _sync_archive_directory, source_dir, dest_archive_path
        )
