"""Authentication router for admin login, token refresh, and user profile inspection."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user, get_auth_service
from src.database.models.users import User
from src.schemas.user import LoginRequest, LoginResponse, TokenRefreshRequest, UserDTO
from src.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    AccountDisabledError,
    InvalidRefreshTokenError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse, summary="Admin login")
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """Authenticate user credentials and return signed JWT access and refresh tokens."""
    try:
        return await auth_service.authenticate(
            username=request.username,
            password=request.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AccountDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post("/refresh", summary="Refresh JWT access token")
async def refresh_token(
    request: TokenRefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """Validate a signed refresh token and issue a fresh access token."""
    try:
        new_access_token = await auth_service.refresh_access_token(request.refresh_token)
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
        }
    except InvalidRefreshTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.get("/me", response_model=UserDTO, summary="Get current authenticated user profile")
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserDTO:
    """Return the profile information of the currently authenticated admin/viewer user."""
    return UserDTO.model_validate(current_user)
