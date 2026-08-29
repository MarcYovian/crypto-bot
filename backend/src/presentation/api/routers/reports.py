"""FastAPI controller for generating and downloading performance reports."""

import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from src.infrastructure.persistence.models.users import User
from src.application.use_cases.reports import ExportTradesCsvUseCase
from src.presentation.api.deps import get_current_user, get_export_trades_csv_use_case
from src.domain.exceptions.system import InvalidDateRangeError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get(
    "/export/csv",
    summary="Export trade history as CSV file",
    description="Download a complete RFC 4180 CSV export of closed trade history with metrics.",
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV file download of trading performance history.",
        }
    },
)
async def export_trades_csv(
    start_date: Optional[date] = Query(
        default=None,
        description="Inclusive start date (YYYY-MM-DD)",
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Inclusive end date (YYYY-MM-DD)",
    ),
    use_case: ExportTradesCsvUseCase = Depends(get_export_trades_csv_use_case),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream or return CSV file download of closed trades."""
    try:
        csv_content = await use_case.execute(
            start_date=start_date,
            end_date=end_date,
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="trades_report.csv"',
            },
        )
    except InvalidDateRangeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
        logger.error(f"Failed to export trades CSV report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error generating trades CSV: {e}",
        )

