"""FastAPI controller for querying system audit logs."""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.system import LogEntryDTO
from src.application.use_cases.logs import GetLogsUseCase
from src.presentation.api.deps import get_current_user, get_logs_use_case
from src.domain.exceptions.system import InvalidLogLevelError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/logs", tags=["Logs & Audit"])


@router.get(
    "",
    response_model=List[LogEntryDTO],
    summary="Query system audit logs",
    description="Retrieve system audit logs with optional severity level filtering and trace_id correlation.",
)
async def get_logs(
    level: Optional[str] = Query(
        default=None,
        description="Filter log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    ),
    trace_id: Optional[str] = Query(
        default=None,
        description="Filter by correlation trace ID",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum logs to return (default 100, max 1000)",
    ),
    use_case: GetLogsUseCase = Depends(get_logs_use_case),
    current_user: User = Depends(get_current_user),
) -> List[LogEntryDTO]:
    """Retrieve filtered audit logs for system observability."""
    try:
        return await use_case.execute(
            level=level,
            trace_id=trace_id,
            limit=limit,
        )
    except InvalidLogLevelError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error querying audit logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system audit logs.",
        )

