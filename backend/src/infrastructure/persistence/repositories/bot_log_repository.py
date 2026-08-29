"""Data-access repository for system Audit Logs."""

import json
from datetime import datetime, timedelta
from typing import Optional, List, Union, Dict, Any
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.persistence.models import BotLog
from src.presentation.api.schemas.common import BaseSchema
from src.presentation.api.schemas.system import BotLogCreate
from src.infrastructure.persistence.repositories.base import BaseRepository


class BotLogRepository(BaseRepository[BotLog, BotLogCreate, BaseSchema]):
    """CRUD repository for the ``bot_logs`` table."""

    def __init__(self, session: AsyncSession):
        super().__init__(BotLog, session)

    async def create_log(
        self,
        level: str,
        message: str,
        module: Optional[str] = None,
        context: Optional[Union[str, Dict[str, Any]]] = None,
        created_at: Optional[datetime] = None,
    ) -> BotLog:
        """Create and persist a system audit log record.
        
        Args:
            level: Log level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
            message: Log message string.
            module: Calling module or service name.
            context: Contextual JSON string or Python dictionary payload.
            created_at: Optional explicit creation timestamp.
            
        Returns:
            The created BotLog instance.
        """
        ctx_str: Optional[str] = None
        if context is not None:
            if isinstance(context, dict):
                ctx_str = json.dumps(context)
            else:
                ctx_str = str(context)

        log = BotLog(
            level=level.strip().upper(),
            message=message,
            module=module,
            context_json=ctx_str,
            created_at=created_at if created_at is not None else datetime.now(),
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_recent_logs(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        module: Optional[str] = None,
    ) -> List[BotLog]:
        """Fetch recent system logs ordered chronologically descending.
        
        Utilizes index ``idx_bot_logs_level_created``.
        
        Args:
            limit: Maximum log rows.
            level: Optional level filter.
            module: Optional module filter.
            
        Returns:
            List of BotLog instances.
        """
        stmt = select(BotLog).order_by(BotLog.created_at.desc(), BotLog.id.desc()).limit(limit)

        if level is not None:
            stmt = stmt.where(func.upper(BotLog.level) == level.strip().upper())
        if module is not None:
            stmt = stmt.where(func.upper(BotLog.module) == module.strip().upper())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def query_logs(
        self,
        level: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[BotLog]:
        """Query audit logs with optional level filter and trace_id correlation search.

        Args:
            level: Optional severity level (e.g. DEBUG, INFO, WARNING, ERROR, CRITICAL).
            trace_id: Optional correlation trace ID (e.g. sig-a1b2c3d4).
            limit: Maximum log rows to retrieve (capped between 1 and 1000).

        Returns:
            List of BotLog instances matching the search criteria.
        """
        capped_limit = min(max(1, limit), 1000)
        stmt = select(BotLog).order_by(BotLog.created_at.desc(), BotLog.id.desc()).limit(capped_limit)

        if level is not None and level.strip():
            stmt = stmt.where(func.upper(BotLog.level) == level.strip().upper())
        if trace_id is not None and trace_id.strip():
            tid = trace_id.strip()
            stmt = stmt.where(
                (BotLog.context_json.like(f"%{tid}%")) | (BotLog.message.like(f"%{tid}%"))
            )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())


    async def get_error_logs(
        self,
        limit: int = 50,
        start_date: Optional[datetime] = None,
    ) -> List[BotLog]:
        """Fetch recent ERROR and CRITICAL logs for incident monitoring.
        
        Args:
            limit: Maximum log rows.
            start_date: Optional start datetime filter.
            
        Returns:
            List of error BotLog instances.
        """
        stmt = (
            select(BotLog)
            .where(BotLog.level.in_(["ERROR", "CRITICAL"]))
            .order_by(BotLog.created_at.desc(), BotLog.id.desc())
            .limit(limit)
        )
        if start_date is not None:
            stmt = stmt.where(BotLog.created_at >= start_date)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_errors(self, limit: int = 5) -> List[BotLog]:
        """Fetch recent ERROR and CRITICAL logs (alias for get_error_logs)."""
        return await self.get_error_logs(limit=limit)

    async def purge_old_logs(self, days: int = 30) -> int:
        """Purge logs older than specified retention days.
        
        Args:
            days: Retention window in days (default: 30 days).
            
        Returns:
            Number of deleted log rows.
        """
        cutoff = datetime.now() - timedelta(days=days)
        stmt = delete(BotLog).where(BotLog.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
