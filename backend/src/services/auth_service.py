"""Authentication and user management domain service."""

from typing import Optional
import jwt

from src.database.models.users import User
from src.repository.user_repository import UserRepository
from src.schemas.user import LoginResponse, UserDTO
from src.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.domain.exceptions.base import DomainError


class InvalidCredentialsError(DomainError):
    """Raised when authentication credentials are invalid."""


class AccountDisabledError(DomainError):
    """Raised when account is inactive or disabled."""


class InvalidRefreshTokenError(DomainError):
    """Raised when refresh token is malformed, expired, or invalid."""


class AuthService:
    """Business service handling user authentication, credential validation, and JWT token issuance."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def authenticate(self, username: str, password: str) -> LoginResponse:
        """Authenticate user credentials and issue signed JWT access and refresh tokens.

        Args:
            username: User login name.
            password: Plaintext password candidate.

        Returns:
            LoginResponse with access token, refresh token, and user DTO.
        """
        user = await self.user_repo.get_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password.")

        if not user.is_active:
            raise AccountDisabledError("Account is disabled. Please contact administrator.")

        token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserDTO.model_validate(user),
        )

    async def refresh_access_token(self, refresh_token_str: str) -> str:
        """Validate refresh token and issue a fresh access token.

        Args:
            refresh_token_str: JWT refresh token string.

        Returns:
            Fresh JWT access token string.
        """
        try:
            payload = decode_token(refresh_token_str)
            username = payload.get("sub")
            token_type = payload.get("type")

            if not username or token_type != "refresh":
                raise InvalidRefreshTokenError("Invalid refresh token payload.")
        except jwt.ExpiredSignatureError:
            raise InvalidRefreshTokenError("Refresh token has expired. Please login again.")
        except jwt.PyJWTError:
            raise InvalidRefreshTokenError("Could not validate refresh token.")

        user = await self.user_repo.get_by_username(username)
        if not user or not user.is_active:
            raise InvalidRefreshTokenError("User no longer active or exists.")

        token_data = {"sub": user.username, "role": user.role, "user_id": user.id}
        return create_access_token(data=token_data)
