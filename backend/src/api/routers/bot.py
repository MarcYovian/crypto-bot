"""API Router for Bot Operations and Circuit Breaker."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from src.database.models.users import User
from src.schemas.system import (
    BotStatusDTO,
    GenericActionResponse,
    PanicCloseRequest,
    PanicCloseResponseDTO,
)
from src.services.bot_service import BotService
from src.domain.exceptions.system import (
    PanicConfirmationRequiredError,
    BotOperationError,
)
from src.api.deps import (
    get_current_user,
    get_current_admin_user,
    get_bot_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["Bot Operations"])


@router.get(
    "/status",
    response_model=BotStatusDTO,
    summary="Get real-time engine runtime status",
    description="Returns health status, circuit breaker pause state, WebSocket status, and scheduler heartbeat.",
)
async def get_bot_status(
    current_user: User = Depends(get_current_user),
    bot_service: BotService = Depends(get_bot_service),
) -> BotStatusDTO:
    """Retrieve runtime state of the bot engine."""
    return await bot_service.get_bot_status()


@router.post(
    "/pause",
    response_model=GenericActionResponse,
    summary="Pause trading bot manually",
    description="Rejects any new incoming signals until resumed. Open positions remain active.",
)
async def pause_bot(
    admin_user: User = Depends(get_current_admin_user),
    bot_service: BotService = Depends(get_bot_service),
) -> GenericActionResponse:
    """Manually pause bot trading engine (Admin only)."""
    return await bot_service.pause_bot()


@router.post(
    "/resume",
    response_model=GenericActionResponse,
    summary="Resume trading bot",
    description="Re-enables signal ingestion and clears any circuit-breaker pause states.",
)
async def resume_bot(
    admin_user: User = Depends(get_current_admin_user),
    bot_service: BotService = Depends(get_bot_service),
) -> GenericActionResponse:
    """Resume bot trading engine (Admin only)."""
    return await bot_service.resume_bot()


@router.post(
    "/panic",
    response_model=PanicCloseResponseDTO,
    summary="Emergency Panic Close All",
    description="Closes all open positions via Market order and cancels all active orders immediately.",
)
async def panic_close(
    payload: PanicCloseRequest,
    admin_user: User = Depends(get_current_admin_user),
    bot_service: BotService = Depends(get_bot_service),
) -> PanicCloseResponseDTO:
    """Emergency close all open trades and cancel all pending orders (Admin only)."""
    try:
        return await bot_service.panic_close_all(payload.confirmation)
    except PanicConfirmationRequiredError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error during emergency panic close: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Emergency panic close encountered an internal error: {e}",
        )
