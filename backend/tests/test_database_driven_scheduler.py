"""Comprehensive unit and integration tests for Database-Driven Scheduler and MisfirePolicy recovery."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.value_objects.misfire_policy import MisfirePolicy
from src.infrastructure.di.container import container
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange,
    RiskProfile,
    SchedulerTask,
    SchedulerTaskRun,
    Strategy,
    Trade,
    TradingAccount,
)
from src.infrastructure.persistence.repositories.scheduler_task_repository import SchedulerTaskRepository
from src.infrastructure.scheduler import SchedulerService
from src.infrastructure.scheduler.task_registry import DEFAULT_SYSTEM_TASKS, calculate_next_fire_time


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
async def test_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id,
        name="Binance Test Account",
        account_type="FUTURES",
        environment="TESTNET",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    strategy = Strategy(name="Default 3-Tier Strategy", version="1.0.0", is_active=True)
    async_session.add(strategy)
    await async_session.flush()

    profile = RiskProfile(
        name="Conservative 2%",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("6.0"),
        max_open_trade=3,
        is_active=True,
    )
    async_session.add(profile)
    await async_session.commit()

    return {"account": account, "exchange": exchange, "strategy": strategy, "profile": profile}


@pytest.mark.asyncio
async def test_scheduler_task_repository_crud(async_session: AsyncSession):
    """Test SchedulerTaskRepository upsert, retrieval, and run recording."""
    repo = SchedulerTaskRepository(async_session)

    # 1. Upsert task with MisfirePolicy ENUM
    next_time = datetime.now() + timedelta(hours=1)
    task = await repo.upsert_task(
        task_id="test_custom_job",
        name="Custom Test Job",
        cron_expr="0 * * * *",
        misfire_policy=MisfirePolicy.RUN_LATEST_ONCE,
        next_run_at=next_time,
    )
    await async_session.commit()

    assert task.id == "test_custom_job"
    assert task.misfire_policy == MisfirePolicy.RUN_LATEST_ONCE
    assert task.is_active is True

    # 2. Query task
    fetched = await repo.get("test_custom_job")
    assert fetched is not None
    assert fetched.name == "Custom Test Job"

    # 3. Record task run
    started = datetime.now() - timedelta(seconds=2)
    finished = datetime.now()
    run = await repo.record_task_run(
        task_id="test_custom_job",
        started_at=started,
        finished_at=finished,
        status="SUCCESS",
        next_run_at=datetime.now() + timedelta(hours=2),
        duration_ms=2000,
        result_summary={"items_processed": 10},
    )
    await async_session.commit()

    assert run.status == "SUCCESS"
    assert run.duration_ms == 2000

    # 4. Check history
    runs = await repo.get_recent_runs("test_custom_job", limit=10)
    assert len(runs) == 1
    assert runs[0].task_id == "test_custom_job"


@pytest.mark.asyncio
async def test_startup_recovery_seeds_default_tasks(async_session: AsyncSession):
    """Verify that run_startup_recovery automatically seeds 8 default tasks into DB."""
    scheduler = SchedulerService(session=async_session)

    res = await scheduler.run_startup_recovery()
    assert "overdue_count" in res

    repo = SchedulerTaskRepository(async_session)
    tasks = await repo.get_all()
    assert len(tasks) == 8

    task_ids = {t.id for t in tasks}
    for def_task in DEFAULT_SYSTEM_TASKS:
        assert def_task["id"] in task_ids

    # Verify MisfirePolicy ENUMs
    snapshot_task = await repo.get("daily_risk_snapshot")
    assert snapshot_task.misfire_policy == MisfirePolicy.RUN_LATEST_ONCE

    heartbeat_task = await repo.get("heartbeat_health_check")
    assert heartbeat_task.misfire_policy == MisfirePolicy.SKIP_TO_NEXT

    failsafe_task = await repo.get("failsafe_sync_check")
    assert failsafe_task.misfire_policy == MisfirePolicy.IMMEDIATE


@pytest.mark.asyncio
async def test_startup_recovery_handles_overdue_tasks_with_misfire_policy(
    async_session: AsyncSession, test_env: dict
):
    """Test downtime recovery: RUN_LATEST_ONCE is caught up, SKIP_TO_NEXT is skipped."""
    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("5000.0")})
    mock_gateway.fetch_positions = AsyncMock(return_value=[])
    mock_tg = AsyncMock(spec=INotificationGateway)

    scheduler = SchedulerService(
        session=async_session,
        exchange_gateway=mock_gateway,
        notification_gateway=mock_tg,
    )

    # 1. Seed tasks first
    await scheduler.run_startup_recovery()

    repo = SchedulerTaskRepository(async_session)

    # 2. Simulate server downtime: set next_run_at to the past
    past_time = datetime.now() - timedelta(hours=3)

    # daily_risk_snapshot: RUN_LATEST_ONCE -> must execute catch-up
    snap_task = await repo.get("daily_risk_snapshot")
    snap_task.next_run_at = past_time

    # heartbeat_health_check: SKIP_TO_NEXT -> must advance without running
    hb_task = await repo.get("heartbeat_health_check")
    hb_task.next_run_at = past_time

    await async_session.commit()

    # 3. Run recovery
    recovery_res = await scheduler.run_startup_recovery()

    assert "daily_risk_snapshot" in recovery_res["recovered"]
    assert "heartbeat_health_check" in recovery_res["skipped"]

    # Verify heartbeat next_run_at was advanced into the future
    await async_session.refresh(hb_task)
    assert hb_task.next_run_at > datetime.now()


@pytest.mark.asyncio
async def test_dynamic_pause_task_via_database(async_session: AsyncSession):
    """Verify that setting is_active=False in DB immediately pauses task execution."""
    scheduler = SchedulerService(session=async_session)
    await scheduler.run_startup_recovery()

    repo = SchedulerTaskRepository(async_session)
    task = await repo.get("cleanup_orphan_orders")
    task.is_active = False
    await async_session.commit()

    # Execute cleanup job; since is_active=False, it should return 0 / skipped
    result = await scheduler.run_cleanup_orphan_orders_job()
    assert result == 0


@pytest.mark.asyncio
async def test_execution_tracking_records_runs_in_database(
    async_session: AsyncSession, test_env: dict
):
    """Verify that running a job records execution metrics in scheduler_task_runs."""
    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0")})
    mock_tg = AsyncMock(spec=INotificationGateway)

    scheduler = SchedulerService(
        session=async_session,
        exchange_gateway=mock_gateway,
        notification_gateway=mock_tg,
    )
    await scheduler.run_startup_recovery()

    # Run heartbeat health check
    res = await scheduler.run_heartbeat_health_check_job()
    assert res["is_healthy"] is True

    repo = SchedulerTaskRepository(async_session)
    runs = await repo.get_recent_runs("heartbeat_health_check", limit=10)

    assert len(runs) >= 1
    latest_run = runs[0]
    assert latest_run.status == "SUCCESS"
    assert latest_run.duration_ms is not None
    assert latest_run.duration_ms >= 0

    task = await repo.get("heartbeat_health_check")
    assert task.last_status == "SUCCESS"
    assert task.last_run_at is not None


@pytest.mark.asyncio
async def test_scheduler_runner_update_task_schedule_and_metadata(async_session: AsyncSession):
    """Verify unified update_task modifies name, cron_expr, misfire_policy and recalculates next_run_at."""
    scheduler = SchedulerService(session=async_session)
    await scheduler.run_startup_recovery()

    # 1. Update task to run every 30 minutes with new name and policy
    updated_task = await scheduler.update_task(
        task_id="cleanup_orphan_orders",
        name="High Frequency Orphan Cleaner",
        cron_expr="*/30 * * * *",
        misfire_policy=MisfirePolicy.IMMEDIATE,
    )

    assert updated_task.name == "High Frequency Orphan Cleaner"
    assert updated_task.cron_expr == "*/30 * * * *"
    assert updated_task.misfire_policy == MisfirePolicy.IMMEDIATE
    assert updated_task.next_run_at > datetime.now()

    # 2. Verify persisted in DB
    repo = SchedulerTaskRepository(async_session)
    db_task = await repo.get("cleanup_orphan_orders")
    assert db_task.name == "High Frequency Orphan Cleaner"
    assert db_task.cron_expr == "*/30 * * * *"
    assert db_task.misfire_policy == MisfirePolicy.IMMEDIATE


@pytest.mark.asyncio
async def test_scheduler_runner_update_task_invalid_cron_raises_error(async_session: AsyncSession):
    """Verify update_task rejects invalid cron expressions with ValueError."""
    scheduler = SchedulerService(session=async_session)
    await scheduler.run_startup_recovery()

    with pytest.raises(ValueError):
        await scheduler.update_task("cleanup_orphan_orders", cron_expr="invalid_cron_expression")


@pytest.mark.asyncio
async def test_scheduler_runner_update_task_live_pause_and_resume(async_session: AsyncSession):
    """Verify update_task pauses and resumes jobs in live APScheduler and database."""
    scheduler = SchedulerService(session=async_session)
    await scheduler.run_startup_recovery()
    scheduler.start()

    try:
        job = scheduler.scheduler.get_job("daily_risk_snapshot")
        assert job is not None
        assert job.next_run_time is not None

        # 1. Pause job via update_task
        await scheduler.update_task("daily_risk_snapshot", is_active=False)

        job_paused = scheduler.scheduler.get_job("daily_risk_snapshot")
        assert job_paused.next_run_time is None

        repo = SchedulerTaskRepository(async_session)
        task_in_db = await repo.get("daily_risk_snapshot")
        assert task_in_db.is_active is False

        # 2. Resume job via update_task
        await scheduler.update_task("daily_risk_snapshot", is_active=True)

        job_resumed = scheduler.scheduler.get_job("daily_risk_snapshot")
        assert job_resumed.next_run_time is not None

        await async_session.refresh(task_in_db)
        assert task_in_db.is_active is True
    finally:
        scheduler.stop()
