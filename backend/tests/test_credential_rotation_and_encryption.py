"""Tests for TradingCredentialRepository lifecycle, key rotation, and secret masking."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, TradingCredential
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.schemas.master import TradingCredentialCreate, TradingCredentialUpdate

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def cred_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Test Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.commit()
    await async_session.refresh(account)

    return {"exchange": exchange, "account": account}


@pytest.mark.asyncio
async def test_credential_create_and_active_retrieval(async_session: AsyncSession, cred_env: dict):
    """Test creating a trading credential and fetching the active one."""
    env = cred_env
    repo = TradingCredentialRepository(async_session)

    schema = TradingCredentialCreate(
        account_id=env["account"].id,
        key_name="Initial Binance Key",
        api_key="AKIA1234567890TESTKEY",
        secret_key="SECRET9876543210TESTSECRET",
        key_version=1,
        is_active=True,
    )
    cred = await repo.create(schema)
    assert cred.id is not None
    assert cred.encrypted_api_key == "AKIA1234567890TESTKEY"
    assert cred.encrypted_secret_key == "SECRET9876543210TESTSECRET"
    assert cred.is_active is True

    active = await repo.get_active_credential(env["account"].id)
    assert active is not None
    assert active.id == cred.id


@pytest.mark.asyncio
async def test_credential_rotation_lifecycle(async_session: AsyncSession, cred_env: dict):
    """Test key rotation: deactivating old credentials before creating a new active key."""
    env = cred_env
    repo = TradingCredentialRepository(async_session)

    # 1. Create v1 credential
    cred_v1 = await repo.create(
        TradingCredentialCreate(
            account_id=env["account"].id,
            key_name="Binance Key V1",
            api_key="OLD_API_KEY_111111",
            secret_key="OLD_SECRET_KEY_111111",
            key_version=1,
            is_active=True,
        )
    )

    # 2. Deactivate old keys
    deactivated = await repo.deactivate_old_credentials(env["account"].id)
    assert deactivated == 1

    await async_session.refresh(cred_v1)
    assert cred_v1.is_active is False

    # 3. Create v2 credential
    cred_v2 = await repo.create(
        TradingCredentialCreate(
            account_id=env["account"].id,
            key_name="Binance Key V2",
            api_key="NEW_API_KEY_222222",
            secret_key="NEW_SECRET_KEY_222222",
            key_version=2,
            is_active=True,
        )
    )

    # 4. Active credential is now v2
    active = await repo.get_active_credential(env["account"].id)
    assert active is not None
    assert active.id == cred_v2.id
    assert active.key_version == 2
    assert active.encrypted_api_key == "NEW_API_KEY_222222"


@pytest.mark.asyncio
async def test_credential_update_keys(async_session: AsyncSession, cred_env: dict):
    """Test updating existing credential attributes."""
    env = cred_env
    repo = TradingCredentialRepository(async_session)

    cred = await repo.create(
        TradingCredentialCreate(
            account_id=env["account"].id,
            key_name="Temporary Key",
            api_key="TEMP_API_KEY_123456",
            secret_key="TEMP_SECRET_KEY_123456",
            key_version=1,
            is_active=True,
        )
    )

    update_dto = TradingCredentialUpdate(
        key_name="Updated Key Name",
        api_key="UPDATED_API_KEY_9999",
        secret_key="UPDATED_SECRET_KEY_9999",
    )
    updated = await repo.update(cred, update_dto)
    assert updated.key_name == "Updated Key Name"
    assert updated.encrypted_api_key == "UPDATED_API_KEY_9999"
    assert updated.encrypted_secret_key == "UPDATED_SECRET_KEY_9999"
