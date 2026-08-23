"""Authentication router for admin login, token refresh, and user profile inspection."""

from fastapi import APIRouter, Depends, HTTPException, status
import jwt

from src.api.deps import get_current_user, get_user_repo
from src.database.models.users import User
from src.repository.user_repository import UserRepository
from src.schemas.user import LoginRequest, LoginResponse, TokenRefreshRequest, UserDTO
from src.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse, summary="Admin login")
async def login(
    request: LoginRequest,
    user_repo: UserRepository = Depends(get_user_repo),
) -> LoginResponse:
    """Authenticate user credentials and return signed JWT access and refresh tokens."""
    user = await user_repo.get_by_username(request.username)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact administrator.",
        )

    token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=UserDTO.model_validate(user),
    )


@router.post("/refresh", summary="Refresh JWT access token")
async def refresh_token(
    request: TokenRefreshRequest,
    user_repo: UserRepository = Depends(get_user_repo),
) -> dict:
    """Validate a signed refresh token and issue a fresh access token."""
    try:
        payload = decode_token(request.refresh_token)
        username = payload.get("sub")
        token_type = payload.get("type")

        if not username or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_repo.get_by_username(username)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active or exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
    new_access_token = create_access_token(data=token_data)

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserDTO, summary="Get current authenticated user profile")
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserDTO:
    """Return the profile information of the currently authenticated admin/viewer user."""
    return UserDTO.model_validate(current_user)
