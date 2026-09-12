"""Authentication router for admin login, token refresh, and user profile inspection."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.presentation.api.deps import (
    get_current_user,
    get_login_use_case,
    get_refresh_token_use_case,
)
from src.infrastructure.persistence.models.users import User
from src.presentation.api.schemas.user import LoginRequest, LoginResponse, TokenRefreshRequest, UserDTO
from src.application.use_cases.auth import (
    LoginUseCase,
    RefreshTokenUseCase,
)
from src.domain.exceptions.auth import (
    InvalidCredentialsError,
    AccountDisabledError,
    InvalidRefreshTokenError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse, summary="Admin login")
async def login(
    request: LoginRequest,
    use_case: LoginUseCase = Depends(get_login_use_case),
) -> LoginResponse:
    """Authenticate user credentials and return signed JWT access and refresh tokens."""
    try:
        return await use_case.execute(
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
    use_case: RefreshTokenUseCase = Depends(get_refresh_token_use_case),
) -> dict:
    """Validate a signed refresh token and issue a fresh access token."""
    try:
        new_access_token = await use_case.execute(request.refresh_token)
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


@router.get("/me", response_model=UserDTO, summary="Get current logged in user profile")
async def get_me(current_user: User = Depends(get_current_user)) -> UserDTO:
    """Return user details for the active JWT session."""
    return UserDTO.model_validate(current_user)
