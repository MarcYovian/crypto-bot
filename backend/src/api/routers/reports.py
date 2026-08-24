"""FastAPI controller for generating and downloading performance reports."""

import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from src.database.models.users import User
from src.services.report_service import ReportService
from src.api.deps import get_current_user, get_report_service
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
    report_service: ReportService = Depends(get_report_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream or return CSV file download of closed trades."""
    try:
        csv_content = await report_service.export_trades_csv(
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
    except Exception as e:
        logger.error(f"Error exporting trades report CSV: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV report.",
        )
