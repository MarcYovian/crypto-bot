"""Use case for validating refresh tokens and issuing fresh access tokens."""

import jwt
from src.domain.exceptions.auth import InvalidRefreshTokenError
from src.domain.ports.repositories import IUserRepository
from src.utils.security import decode_token, create_access_token


class RefreshTokenUseCase:
    """Use case to validate a JWT refresh token and issue a fresh access token."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self.user_repo = user_repo

    async def execute(self, refresh_token_str: str) -> str:
        """Validate refresh token and issue a fresh access token."""
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
