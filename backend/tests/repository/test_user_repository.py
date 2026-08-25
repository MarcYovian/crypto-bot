"""Unit tests for UserRepository operations and default admin seeding."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.connection import Base
from src.database.models.users import User
from src.repository.user_repository import UserRepository
from src.utils.security import get_password_hash, verify_password

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_get_user(async_session: AsyncSession):
    repo = UserRepository(async_session)
    pwd_hash = get_password_hash("SecretPass123!")

    user = await repo.create_user(
        username="TraderJoe",
        password_hash=pwd_hash,
        role="ADMIN",
        is_active=True,
    )
    assert user.id is not None
    assert user.username == "traderjoe"  # Lowercased
    assert user.role == "ADMIN"
    assert verify_password("SecretPass123!", user.password_hash) is True

    # Test get_by_username case-insensitive
    fetched = await repo.get_by_username("TRADERJOE")
    assert fetched is not None
    assert fetched.id == user.id


@pytest.mark.asyncio
async def test_update_user_password(async_session: AsyncSession):
    repo = UserRepository(async_session)
    user = await repo.create_user(
        username="bob",
        password_hash=get_password_hash("OldPassword123"),
    )

    new_hash = get_password_hash("NewPassword456")
    updated = await repo.update_password(user.id, new_hash)
    assert updated is not None
    assert verify_password("NewPassword456", updated.password_hash) is True
    assert verify_password("OldPassword123", updated.password_hash) is False


@pytest.mark.asyncio
async def test_ensure_default_admin_seeding(async_session: AsyncSession):
    repo = UserRepository(async_session)
    default_hash = get_password_hash("Admin12345!")

    # 1. First run: table is empty, seeds default admin
    admin = await repo.ensure_default_admin("admin", default_hash)
    assert admin.username == "admin"
    assert admin.role == "ADMIN"

    # 2. Second run: returns existing admin without duplicate
    admin2 = await repo.ensure_default_admin("admin", default_hash)
    assert admin2.id == admin.id
