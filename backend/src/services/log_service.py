"""Domain service for querying and managing application audit logs."""

import re
import json
from typing import Optional, List
from src.repository.bot_log_repository import BotLogRepository
from src.schemas.system import LogEntryDTO
from src.domain.exceptions.system import InvalidLogLevelError

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
TRACE_ID_REGEX = re.compile(r"(sig-[a-zA-Z0-9_-]+)")


class LogService:
    """Service handling system audit logs filtering and trace_id correlation."""

    def __init__(self, log_repo: BotLogRepository) -> None:
        self.log_repo = log_repo

    async def get_logs(
        self,
        level: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[LogEntryDTO]:
        """Fetch audit logs filtered by severity and/or trace_id correlation.

        Args:
            level: Optional severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            trace_id: Optional correlation trace identifier.
            limit: Maximum logs to retrieve.

        Returns:
            List of LogEntryDTO instances.

        Raises:
            InvalidLogLevelError: If provided level is not in allowed set.
        """
        if level is not None and level.strip():
            clean_level = level.strip().upper()
            if clean_level not in VALID_LOG_LEVELS:
                raise InvalidLogLevelError(
                    f"Invalid log level '{level}'. Allowed levels: {', '.join(sorted(VALID_LOG_LEVELS))}."
                )
        else:
            clean_level = None

        logs = await self.log_repo.query_logs(
            level=clean_level,
            trace_id=trace_id,
            limit=limit,
        )

        results: List[LogEntryDTO] = []
        for l in logs:
            extracted_tid: Optional[str] = None
            if l.context_json:
                try:
                    ctx_dict = json.loads(l.context_json)
                    if isinstance(ctx_dict, dict) and "trace_id" in ctx_dict:
                        extracted_tid = str(ctx_dict["trace_id"])
                except Exception:
                    pass

            if not extracted_tid and l.context_json:
                match = TRACE_ID_REGEX.search(l.context_json)
                if match:
                    extracted_tid = match.group(1)

            if not extracted_tid and l.message:
                match = TRACE_ID_REGEX.search(l.message)
                if match:
                    extracted_tid = match.group(1)

            results.append(
                LogEntryDTO(
                    id=l.id,
                    level=l.level,
                    module=l.module,
                    message=l.message,
                    trace_id=extracted_tid,
                    created_at=l.created_at,
                )
            )

        return results
