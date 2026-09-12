"""Comprehensive unit tests for BotSettingRepository, BotLogRepository, and centralized repository exports."""

import json
from datetime import datetime, timedelta
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import BotSetting, BotLog
from src.presentation.api.schemas.system import BotSettingCreate, BotLogCreate
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
import src.infrastructure.persistence.repositories as repo_package

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
async def test_bot_setting_upsert_and_get_value(async_session: AsyncSession):
    """Test upserting a setting value and updating it without duplication."""
    setting_repo = BotSettingRepository(async_session)

    # 1. Insert initial
    s1 = await setting_repo.set_value("DEFAULT_LEVERAGE", "15", category="TRADING", setting_type="INTEGER")
    assert s1.key == "DEFAULT_LEVERAGE"
    assert s1.value == "15"

    val1 = await setting_repo.get_value("DEFAULT_LEVERAGE")
    assert val1 == "15"

    # 2. Update existing key
    s2 = await setting_repo.set_value("default_leverage", "20", category="TRADING", setting_type="INTEGER")
    assert s2.value == "20"

    val2 = await setting_repo.get_value("DEFAULT_LEVERAGE")
    assert val2 == "20"
    assert await setting_repo.count() == 1


@pytest.mark.asyncio
async def test_bot_setting_type_helpers(async_session: AsyncSession):
    """Test type-casting helpers: get_bool, get_int, get_float, get_json."""
    setting_repo = BotSettingRepository(async_session)

    await setting_repo.set_value("AUTO_TRADE_ENABLED", "true", category="TRADING", setting_type="BOOLEAN")
    await setting_repo.set_value("MAX_OPEN_POSITIONS", "5", category="RISK", setting_type="INTEGER")
    await setting_repo.set_value("MAX_RISK_PERCENT", "2.75", category="RISK", setting_type="FLOAT")
    await setting_repo.set_value("ENABLED_PAIRS", '["BTCUSDT", "ETHUSDT"]', category="TRADING", setting_type="JSON")

    # Booleans
    assert await setting_repo.get_bool("AUTO_TRADE_ENABLED") is True
    assert await setting_repo.get_bool("NON_EXISTING", default=False) is False

    # Integers
    assert await setting_repo.get_int("MAX_OPEN_POSITIONS") == 5
    assert await setting_repo.get_int("NON_EXISTING", default=10) == 10

    # Floats
    assert await setting_repo.get_float("MAX_RISK_PERCENT") == 2.75
    assert await setting_repo.get_float("NON_EXISTING", default=1.5) == 1.5

    # JSON
    pairs = await setting_repo.get_json("ENABLED_PAIRS")
    assert pairs == ["BTCUSDT", "ETHUSDT"]
    assert await setting_repo.get_json("NON_EXISTING", default={}) == {}


@pytest.mark.asyncio
async def test_bot_setting_get_all_by_category_and_as_dict(async_session: AsyncSession):
    """Test category grouping and dictionary serialization for in-memory cache."""
    setting_repo = BotSettingRepository(async_session)

    await setting_repo.set_value("TG_BOT_TOKEN", "123456:ABC", category="TELEGRAM")
    await setting_repo.set_value("TG_CHAT_ID", "987654321", category="TELEGRAM")
    await setting_repo.set_value("APP_ENV", "PRODUCTION", category="SYSTEM")

    tg_settings = await setting_repo.get_all_by_category("telegram")
    assert len(tg_settings) == 2
    assert {s.key for s in tg_settings} == {"TG_BOT_TOKEN", "TG_CHAT_ID"}

    all_dict = await setting_repo.get_all_as_dict()
    assert all_dict["TG_BOT_TOKEN"] == "123456:ABC"
    assert all_dict["APP_ENV"] == "PRODUCTION"


@pytest.mark.asyncio
async def test_bot_log_create_and_filter_by_level(async_session: AsyncSession):
    """Test creating logs and filtering by level and module."""
    log_repo = BotLogRepository(async_session)

    await log_repo.create_log("INFO", "Bot service started", module="SYSTEM")
    await log_repo.create_log("INFO", "WebSocket connected", module="BINANCE")
    await log_repo.create_log("ERROR", "Order execution failed: insufficient margin", module="ORDER_ENGINE")

    all_logs = await log_repo.get_recent_logs()
    assert len(all_logs) == 3

    error_logs = await log_repo.get_recent_logs(level="ERROR")
    assert len(error_logs) == 1
    assert error_logs[0].module == "ORDER_ENGINE"

    binance_logs = await log_repo.get_recent_logs(module="BINANCE")
    assert len(binance_logs) == 1
    assert binance_logs[0].message == "WebSocket connected"


@pytest.mark.asyncio
async def test_bot_log_json_context_and_error_query(async_session: AsyncSession):
    """Test logging context dictionary and querying error logs."""
    log_repo = BotLogRepository(async_session)

    ctx = {"trade_id": 42, "symbol": "BTCUSDT", "error_code": -2019}
    await log_repo.create_log("CRITICAL", "API key permission denied", module="SECURITY", context=ctx)

    error_list = await log_repo.get_error_logs(limit=10)
    assert len(error_list) == 1
    assert error_list[0].level == "CRITICAL"
    assert error_list[0].context_json is not None

    parsed_ctx = json.loads(error_list[0].context_json)
    assert parsed_ctx["trade_id"] == 42
    assert parsed_ctx["error_code"] == -2019


@pytest.mark.asyncio
async def test_bot_log_purge_old_records(async_session: AsyncSession):
    """Test purging logs older than retention period."""
    log_repo = BotLogRepository(async_session)

    now = datetime.now()
    # Old log (created 45 days ago)
    await log_repo.create_log("INFO", "Old system heartbeat", module="HEARTBEAT", created_at=now - timedelta(days=45))
    # Recent log (created 5 days ago)
    await log_repo.create_log("INFO", "Recent log", module="HEARTBEAT", created_at=now - timedelta(days=5))

    assert await log_repo.count() == 2

    # Purge older than 30 days
    purged_count = await log_repo.purge_old_logs(days=30)
    assert purged_count == 1
    assert await log_repo.count() == 1


def test_repository_package_central_exports():
    """Verify that all 19 repository classes are correctly exported from src.infrastructure.persistence.repositories."""
    expected_exports = [
        "BaseRepository",
        "ExchangeRepository",
        "TradingAccountRepository",
        "TradingCredentialRepository",
        "InstrumentRepository",
        "WatchlistRepository",
        "StrategyRepository",
        "SignalProviderRepository",
        "RiskProfileRepository",
        "SignalRepository",
        "DailyRiskRepository",
        "TradeRiskRepository",
        "TradeRepository",
        "OrderRepository",
        "ExecutionRepository",
        "TradeEventRepository",
        "TradeSummaryRepository",
        "BotSettingRepository",
        "BotLogRepository",
    ]

    for export_name in expected_exports:
        assert hasattr(repo_package, export_name), f"Missing export {export_name} in src.infrastructure.persistence.repositories"
