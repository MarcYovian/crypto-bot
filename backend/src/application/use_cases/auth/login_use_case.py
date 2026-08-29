"""Use case for authenticating users and issuing JWT tokens."""

from src.domain.exceptions.auth import InvalidCredentialsError, AccountDisabledError
from src.domain.ports.repositories import IUserRepository
from src.presentation.api.schemas.user import LoginResponse, UserDTO
from src.utils.security import verify_password, create_access_token, create_refresh_token


class LoginUseCase:
    """Use case to authenticate user credentials and issue signed JWT access and refresh tokens."""

    def __init__(self, user_repo: IUserRepository) -> None:
        self.user_repo = user_repo

    async def execute(self, username: str, password: str) -> LoginResponse:
        """Authenticate user credentials and issue signed JWT access and refresh tokens."""
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
