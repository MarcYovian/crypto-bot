"""Use case for purging system audit logs older than a retention threshold."""

import logging
from src.domain.ports.repositories import IBotLogRepository

logger = logging.getLogger(__name__)


class PurgeOldLogsUseCase:
    """Use case to delete historical audit logs exceeding the retention period."""

    def __init__(self, log_repo: IBotLogRepository) -> None:
        self.log_repo = log_repo

    async def execute(self, days: int = 30) -> int:
        """Purge system logs older than the specified retention days.

        Args:
            days: Retention threshold in days (default 30).

        Returns:
            The number of purged log records.
        """
        deleted_count = await self.log_repo.purge_old_logs(days=days)
        logger.info("Purged %d system logs older than %d days.", deleted_count, days)
        return deleted_count
