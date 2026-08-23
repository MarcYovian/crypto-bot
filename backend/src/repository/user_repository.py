"""Repository implementation for User model operations and authentication queries."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.users import User
from src.schemas.user import UserCreateRequest
from src.repository.base import BaseRepository


class UserRepository(BaseRepository[User, UserCreateRequest, UserCreateRequest]):
    """Data access repository for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_username(self, username: str) -> Optional[User]:
        """Fetch an active or inactive user by unique username."""
        clean_username = username.strip().lower()
        stmt = select(User).where(User.username == clean_username)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "ADMIN",
        is_active: bool = True,
    ) -> User:
        """Create and persist a new user account."""
        user = User(
            username=username.strip().lower(),
            password_hash=password_hash,
            role=role.upper(),
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_password(self, user_id: int, new_password_hash: str) -> Optional[User]:
        """Update password hash for an existing user."""
        user = await self.get(user_id)
        if not user:
            return None
        user.password_hash = new_password_hash
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def ensure_default_admin(self, default_username: str, default_password_hash: str) -> User:
        """Seed a default admin user if no users currently exist in the database."""
        existing_admin = await self.get_by_username(default_username)
        if existing_admin:
            return existing_admin

        # Count total users
        all_users = await self.get_multi(limit=1)
        if len(all_users) == 0:
            return await self.create_user(
                username=default_username,
                password_hash=default_password_hash,
                role="ADMIN",
                is_active=True,
            )
        return all_users[0]
