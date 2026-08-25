"""API Router for Bot Configuration Settings & Credentials Management."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from src.database.models.users import User
from src.schemas.system import (
    BotSettingsDTO,
    BotSettingsUpdateRequest,
    TradingCredentialCreateRequest,
    CredentialSaveResponseDTO,
)
from src.services.bot_service import BotService
from src.domain.exceptions.system import InvalidSettingsValueError
from src.domain.exceptions.exchange import ExchangeAuthError
from src.utils.cache import in_memory_cache
from src.api.deps import (
    get_current_user,
    get_current_admin_user,
    get_bot_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["Settings & Credentials"])


@router.get(
    "",
    response_model=BotSettingsDTO,
    summary="Get active bot settings & risk profile",
    description="Returns current risk parameters and runtime configuration.",
)
async def get_settings(
    current_user: User = Depends(get_current_user),
    bot_service: BotService = Depends(get_bot_service),
) -> BotSettingsDTO:
    """Fetch active configuration settings (cached)."""
    cache_key = "settings:active"
    cached_data = await in_memory_cache.get(cache_key)
    if cached_data is not None and isinstance(cached_data, dict):
        return BotSettingsDTO(**cached_data)

    settings_dto = await bot_service.get_settings()
    await in_memory_cache.set(cache_key, settings_dto.model_dump(), ttl_seconds=60)
    return settings_dto


@router.put(
    "",
    response_model=BotSettingsDTO,
    summary="Update bot settings & risk profile",
    description="Modifies default leverage, risk percent, confidence threshold, and max daily loss limits (Admin only).",
)
async def update_settings(
    payload: BotSettingsUpdateRequest,
    admin_user: User = Depends(get_current_admin_user),
    bot_service: BotService = Depends(get_bot_service),
) -> BotSettingsDTO:
    """Update bot configuration settings (Admin only)."""
    try:
        return await bot_service.update_settings(payload)
    except InvalidSettingsValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error updating bot settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {e}",
        )


@router.post(
    "/credentials",
    response_model=CredentialSaveResponseDTO,
    summary="Add or rotate Binance API Key & Secret with handshake test",
    description="Validates credentials against live Binance endpoint and stores encrypted key pair (Admin only).",
)
async def save_credentials(
    payload: TradingCredentialCreateRequest,
    admin_user: User = Depends(get_current_admin_user),
    bot_service: BotService = Depends(get_bot_service),
) -> CredentialSaveResponseDTO:
    """Register or rotate trading API credentials with handshake check (Admin only)."""
    try:
        return await bot_service.save_and_test_credentials(payload)
    except ExchangeAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error saving trading credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {e}",
        )
