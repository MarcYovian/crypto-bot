"""Unit tests for TradingAccountRepository and TradingCredentialRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, TradingCredential
from src.schemas.master import (
    ExchangeCreate,
    TradingAccountCreate,
    TradingCredentialCreate,
)
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create a fresh in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_trading_account_create_and_query_active(async_session: AsyncSession):
    """Test creating a trading account and querying the active account."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))

    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Binance Testnet Account",
        account_type="FUTURES",
        environment="TESTNET",
        is_active=True
    ))

    assert account.id is not None
    assert account.environment == "TESTNET"

    active_acc = await acc_repo.get_active_account(exchange.id)
    assert active_acc is not None
    assert active_acc.id == account.id
    assert active_acc.name == "Binance Testnet Account"


@pytest.mark.asyncio
async def test_trading_account_filter_environment(async_session: AsyncSession):
    """Test filtering accounts by trading environment."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))

    await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Testnet Acc",
        environment="TESTNET",
        is_active=True
    ))
    await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Mainnet Acc",
        environment="MAINNET",
        is_active=True
    ))

    testnet_accs = await acc_repo.get_by_environment("testnet")
    assert len(testnet_accs) == 1
    assert testnet_accs[0].name == "Testnet Acc"

    mainnet_accs = await acc_repo.get_by_environment("MAINNET")
    assert len(mainnet_accs) == 1
    assert mainnet_accs[0].name == "Mainnet Acc"


@pytest.mark.asyncio
async def test_trading_credential_create_and_fetch_active(async_session: AsyncSession):
    """Test saving credentials and fetching the active key version."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="MAINNET",
        is_active=True
    ))

    # Save credential (simulated encrypted values)
    cred = await cred_repo.create({
        "account_id": account.id,
        "key_name": "API Key v1",
        "encrypted_api_key": "enc_api_key_12345678",
        "encrypted_secret_key": "enc_secret_key_87654321",
        "key_version": 1,
        "is_active": True
    })

    assert cred.id is not None
    assert cred.key_version == 1

    active_cred = await cred_repo.get_active_credential(account.id)
    assert active_cred is not None
    assert active_cred.id == cred.id
    assert active_cred.key_name == "API Key v1"


@pytest.mark.asyncio
async def test_credential_rotation_deactivate_old(async_session: AsyncSession):
    """Test deactivating old credentials during rotation."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Rotation Test Account",
        environment="TESTNET",
        is_active=True
    ))

    # Version 1
    await cred_repo.create({
        "account_id": account.id,
        "key_name": "Key v1",
        "encrypted_api_key": "enc_v1",
        "encrypted_secret_key": "enc_sec_v1",
        "key_version": 1,
        "is_active": True
    })

    # Rotate: deactivate old
    deactivated_count = await cred_repo.deactivate_old_credentials(account.id)
    assert deactivated_count == 1

    # Add Version 2
    v2 = await cred_repo.create({
        "account_id": account.id,
        "key_name": "Key v2",
        "encrypted_api_key": "enc_v2",
        "encrypted_secret_key": "enc_sec_v2",
        "key_version": 2,
        "is_active": True
    })

    current_active = await cred_repo.get_active_credential(account.id)
    assert current_active is not None
    assert current_active.id == v2.id
    assert current_active.key_version == 2
