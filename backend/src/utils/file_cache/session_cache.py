"""Session cache logger for time-bound session context and runtime states.

Inspired by Odoo session.py TTL expiration and structured session management.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

from src.utils.file_cache.base_cache import (
    BaseFileCacheLogger,
    clean_path_name,
)


class SessionCacheLogger(BaseFileCacheLogger):
    """Manages time-bound file-based session states with automatic TTL expiration."""

    def __init__(
        self,
        session_type: str = "user_session",
        base_path: Optional[str] = None,
        default_ttl_seconds: int = 3600,
        chat_id: Optional[Union[int, str]] = None,
    ) -> None:
        super().__init__(base_path=base_path, chat_id=chat_id)
        self.session_type = clean_path_name(session_type) or "user_session"
        self.default_ttl_seconds = default_ttl_seconds

        root = base_path or "/var/log/cryptobot/sessions/"
        self.session_dir = os.path.join(root, self.session_type, self.chat_id)

    def is_expired(self, session_payload: Dict[str, Any]) -> bool:
        """Check if a session payload has exceeded its expiration timestamp."""
        if not isinstance(session_payload, dict):
            return True

        expired_at_str = session_payload.get("expired_at")
        if not expired_at_str:
            return False

        try:
            # Handle ISO format or fallback space format
            if "T" in expired_at_str:
                expired_date = datetime.fromisoformat(expired_at_str)
            else:
                expired_date = datetime.strptime(expired_at_str, "%Y-%m-%d %H:%M:%S")

            return datetime.now() > expired_date
        except Exception:
            return True

    async def write_session(
        self,
        session_id: str,
        data: Any,
        ttl_seconds: Optional[int] = None,
    ) -> str:
        """Atomically persist session data with TTL expiration."""
        clean_sid = clean_path_name(session_id)
        if not clean_sid:
            return ""

        now = datetime.now()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expired_at = now + timedelta(seconds=ttl) if ttl > 0 else None

        # If ttl <= 0 explicitly passed, mark as immediately expired in the past
        if ttl == 0:
            expired_at = now - timedelta(seconds=1)

        session_payload = {
            "session_id": clean_sid,
            "session_type": self.session_type,
            "created_at": now.isoformat(),
            "expired_at": expired_at.isoformat() if expired_at else None,
            "data": data,
        }

        filename = f"{clean_sid}.json"
        return await self.write_file_atomic(
            directory=self.session_dir,
            filename=filename,
            data=session_payload,
            sanitize=True,
        )

    async def read_session(
        self,
        session_id: str,
        auto_cleanup: bool = True,
    ) -> Optional[Any]:
        """Read and validate session by ID. Returns data payload or None if expired."""
        clean_sid = clean_path_name(session_id)
        if not clean_sid:
            return None

        filename = f"{clean_sid}.json"
        file_path = os.path.join(self.session_dir, filename)

        payload = await self.read_file_json(file_path)
        if not payload:
            return None

        if self.is_expired(payload):
            if auto_cleanup:
                await self.remove_file(file_path)
            return None

        return payload.get("data")

    async def remove_session(self, session_id: str) -> bool:
        """Explicitly remove a session file."""
        clean_sid = clean_path_name(session_id)
        if not clean_sid:
            return False

        filename = f"{clean_sid}.json"
        file_path = os.path.join(self.session_dir, filename)
        return await self.remove_file(file_path)
