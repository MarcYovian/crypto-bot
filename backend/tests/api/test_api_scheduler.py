"""Comprehensive API integration test suite for Scheduler & Cron Jobs management.

Covers 5 test pillars:
1. Positive Cases
2. Negative Cases
3. Edge Cases
4. Logic Cases
5. Security Cases
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.value_objects.misfire_policy import MisfirePolicy
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange,
    RiskProfile,
    SchedulerTask,
    Strategy,
    TradingAccount,
)
from src.infrastructure.persistence.repositories.scheduler_task_repository import SchedulerTaskRepository
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.infrastructure.scheduler.scheduler_runner import SchedulerRunner
from src.infrastructure.scheduler.task_registry import (
    DEFAULT_SYSTEM_TASKS,
    calculate_next_fire_time,
    cron_to_human_interval,
    interval_to_cron,
)
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session, get_scheduler_runner
from src.utils.cache import in_memory_cache
from src.utils.security import get_password_hash

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    """Create isolated test database, seed users, default scheduler tasks, and initialize AsyncClient."""
    await in_memory_cache.clear()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Setup mock gateways
    mock_exchange = AsyncMock(spec=IExchangeGateway)
    mock_exchange.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("5000.0")})
    mock_exchange.fetch_positions = AsyncMock(return_value=[])
    mock_tg = AsyncMock(spec=INotificationGateway)

    # Instantiate test scheduler
    test_scheduler = SchedulerRunner(
        session_factory=session_factory,
        exchange_gateway=mock_exchange,
        notification_gateway=mock_tg,
    )

    app = create_app()

    async def override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def override_get_scheduler_runner():
        return test_scheduler

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_scheduler_runner] = override_get_scheduler_runner

    # Seed Database
    async with session_factory() as session:
        # 1. Users (Admin & Viewer)
        user_repo = UserRepository(session)
        await user_repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )
        await user_repo.create_user(
            username="viewer",
            password_hash=get_password_hash("ViewerPass123!"),
            role="VIEWER",
            is_active=True,
        )

        # 2. Master entities for background use cases
        exchange = Exchange(id=1, code="BINANCE", name="Binance Futures", status=True)
        session.add(exchange)
        await session.flush()

        account = TradingAccount(
            id=1,
            exchange_id=1,
            name="Main Futures",
            account_type="FUTURES",
            environment="TESTNET",
            is_active=True,
        )
        session.add(account)

        strategy = Strategy(name="Default 3-Tier Strategy", version="1.0.0", is_active=True)
        session.add(strategy)

        risk_profile = RiskProfile(
            name="Conservative 2%",
            risk_percent=Decimal("2.0"),
            max_daily_loss=Decimal("6.0"),
            max_open_trade=3,
            is_active=True,
        )
        session.add(risk_profile)
        await session.flush()

        # 3. Seed 8 Default Scheduler Tasks
        task_repo = SchedulerTaskRepository(session)
        for def_task in DEFAULT_SYSTEM_TASKS:
            next_fire = calculate_next_fire_time(def_task["cron_expr"])
            await task_repo.upsert_task(
                task_id=def_task["id"],
                name=def_task["name"],
                cron_expr=def_task["cron_expr"],
                misfire_policy=def_task["misfire_policy"],
                next_run_at=next_fire,
            )

        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory, test_scheduler

    await engine.dispose()


async def get_admin_token(client: AsyncClient) -> str:
    res = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "AdminPass123!"})
    return res.json()["access_token"]


async def get_viewer_token(client: AsyncClient) -> str:
    res = await client.post("/api/v1/auth/login", json={"username": "viewer", "password": "ViewerPass123!"})
    return res.json()["access_token"]


# =============================================================================
# 1. POSITIVE CASES
# =============================================================================
@pytest.mark.asyncio
async def test_list_scheduler_tasks_success(app_and_client):
    """GET /api/v1/scheduler/tasks returns all 8 tasks enriched with human-friendly interval fields."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get("/api/v1/scheduler/tasks", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 8

    # Verify enrichment fields
    task_ids = {t["id"] for t in data}
    assert "daily_risk_snapshot" in task_ids
    assert "cleanup_orphan_orders" in task_ids

    cleanup_task = next(t for t in data if t["id"] == "cleanup_orphan_orders")
    assert cleanup_task["interval_value"] == 30
    assert cleanup_task["interval_unit"] == "MINUTES"
    assert "30 minutes" in cleanup_task["cron_human"]
    assert cleanup_task["cron_expr"] == "0,30 * * * *"
    assert cleanup_task["is_active"] is True


@pytest.mark.asyncio
async def test_list_scheduler_tasks_filter_by_is_active(app_and_client):
    """GET /api/v1/scheduler/tasks?is_active=false returns only paused tasks."""
    client, session_factory, _ = app_and_client
    token = await get_admin_token(client)

    # Pause one task in DB
    async with session_factory() as session:
        task_repo = SchedulerTaskRepository(session)
        task = await task_repo.get("purge_old_logs")
        task.is_active = False
        await session.commit()

    res = await client.get(
        "/api/v1/scheduler/tasks?is_active=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["id"] == "purge_old_logs"
    assert data[0]["is_active"] is False


@pytest.mark.asyncio
async def test_get_scheduler_task_detail_success(app_and_client):
    """GET /api/v1/scheduler/tasks/{task_id} returns task detail and recent_runs array."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/scheduler/tasks/daily_risk_snapshot",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "daily_risk_snapshot"
    assert data["misfire_policy"] == "RUN_LATEST_ONCE"
    assert "recent_runs" in data
    assert isinstance(data["recent_runs"], list)


@pytest.mark.asyncio
async def test_patch_scheduler_task_via_interval_unit_success(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} via interval_value + interval_unit updates cron_expr."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    payload = {
        "name": "Super Fast Orphan Cleaner",
        "interval_value": 15,
        "interval_unit": "MINUTES",
    }
    res = await client.patch(
        "/api/v1/scheduler/tasks/cleanup_orphan_orders",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Super Fast Orphan Cleaner"
    assert data["cron_expr"] == "*/15 * * * *"
    assert data["interval_value"] == 15
    assert data["interval_unit"] == "MINUTES"
    assert "15 minutes" in data["cron_human"]


@pytest.mark.asyncio
async def test_patch_scheduler_task_via_raw_cron_success(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} via raw cron_expr updates correctly."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    payload = {"cron_expr": "0 */2 * * *"}
    res = await client.patch(
        "/api/v1/scheduler/tasks/heartbeat_health_check",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["cron_expr"] == "0 */2 * * *"
    assert data["interval_value"] == 2
    assert data["interval_unit"] == "HOURS"


@pytest.mark.asyncio
async def test_trigger_scheduler_task_success(app_and_client):
    """POST /api/v1/scheduler/tasks/{task_id}/trigger executes job on-demand and returns 200."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/scheduler/tasks/heartbeat_health_check/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["task_id"] == "heartbeat_health_check"
    assert data["status"] == "SUCCESS"
    assert "started_at" in data
    assert data["duration_ms"] is not None


@pytest.mark.asyncio
async def test_get_scheduler_task_runs_success(app_and_client):
    """GET /api/v1/scheduler/tasks/{task_id}/runs returns execution history logs."""
    client, session_factory, _ = app_and_client
    token = await get_admin_token(client)

    # Insert a run directly in DB
    async with session_factory() as session:
        task_repo = SchedulerTaskRepository(session)
        await task_repo.record_task_run(
            task_id="daily_performance_report",
            started_at=datetime.now() - timedelta(seconds=1),
            finished_at=datetime.now(),
            status="SUCCESS",
            duration_ms=1000,
            result_summary="Report dispatched",
        )
        await session.commit()

    res = await client.get(
        "/api/v1/scheduler/tasks/daily_performance_report/runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["task_id"] == "daily_performance_report"
    assert data[0]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_trigger_scheduler_recovery_success(app_and_client):
    """POST /api/v1/scheduler/recovery triggers downtime scan and returns report."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/scheduler/recovery",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "overdue_count" in data
    assert "recovered" in data
    assert "skipped" in data


# =============================================================================
# 2. NEGATIVE CASES
# =============================================================================
@pytest.mark.asyncio
async def test_get_scheduler_task_detail_not_found(app_and_client):
    """GET /api/v1/scheduler/tasks/{task_id} with invalid id returns 404."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/scheduler/tasks/non_existent_task",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_scheduler_task_not_found(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} with invalid id returns 404."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/non_existent_task",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Unknown"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_patch_scheduler_task_invalid_cron_syntax(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} with invalid cron syntax returns 400."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/cleanup_orphan_orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"cron_expr": "invalid cron * *"},
    )
    assert res.status_code == 400
    assert "invalid" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_scheduler_task_invalid_interval_value(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} with interval_value <= 0 returns 422."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/cleanup_orphan_orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"interval_value": 0, "interval_unit": "MINUTES"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_trigger_scheduler_task_not_found(app_and_client):
    """POST /api/v1/scheduler/tasks/{task_id}/trigger with invalid id returns 404."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/scheduler/tasks/non_existent_task/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_scheduler_task_runs_not_found(app_and_client):
    """GET /api/v1/scheduler/tasks/{task_id}/runs with invalid id returns 404."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/scheduler/tasks/non_existent_task/runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


# =============================================================================
# 3. EDGE CASES
# =============================================================================
@pytest.mark.asyncio
async def test_patch_scheduler_task_empty_payload(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} with empty JSON {} returns 200 unchanged."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/cleanup_orphan_orders",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "cleanup_orphan_orders"


@pytest.mark.asyncio
async def test_patch_scheduler_task_only_name(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} updating only name preserves cron schedule."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/cleanup_orphan_orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Renamed Task Only"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Renamed Task Only"
    assert data["cron_expr"] == "0,30 * * * *"


@pytest.mark.asyncio
async def test_patch_scheduler_task_pause_and_resume(app_and_client):
    """PATCH /api/v1/scheduler/tasks/{task_id} with is_active toggles pause and resume."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    # 1. Pause
    res1 = await client.patch(
        "/api/v1/scheduler/tasks/sync_instruments_metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    assert res1.status_code == 200
    assert res1.json()["is_active"] is False

    # 2. Resume
    res2 = await client.patch(
        "/api/v1/scheduler/tasks/sync_instruments_metadata",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": True},
    )
    assert res2.status_code == 200
    assert res2.json()["is_active"] is True


@pytest.mark.asyncio
async def test_patch_scheduler_task_boundary_units(app_and_client):
    """Test interval_to_cron converter with value=1 for all 5 units."""
    assert interval_to_cron(1, "MINUTES") == "* * * * *"
    assert interval_to_cron(1, "HOURS") == "0 * * * *"
    assert interval_to_cron(1, "DAYS") == "0 0 * * *"
    assert interval_to_cron(1, "WEEKS") == "0 0 * * 0"
    assert interval_to_cron(1, "MONTHS") == "0 0 1 * *"


@pytest.mark.asyncio
async def test_get_scheduler_task_runs_extreme_limits(app_and_client):
    """GET /api/v1/scheduler/tasks/{task_id}/runs with limit=1 and limit=100."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/scheduler/tasks/daily_risk_snapshot/runs?limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    res_max = await client.get(
        "/api/v1/scheduler/tasks/daily_risk_snapshot/runs?limit=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_max.status_code == 200


# =============================================================================
# 4. LOGIC CASES
# =============================================================================
@pytest.mark.asyncio
async def test_patch_task_recalculates_next_run_at(app_and_client):
    """Verify that PATCH schedule causes next_run_at to be immediately recalculated into the future."""
    client, _, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.patch(
        "/api/v1/scheduler/tasks/daily_risk_snapshot",
        headers={"Authorization": f"Bearer {token}"},
        json={"interval_value": 10, "interval_unit": "MINUTES"},
    )
    assert res.status_code == 200
    data = res.json()
    next_run = datetime.fromisoformat(data["next_run_at"])
    assert next_run > datetime.now()


@pytest.mark.asyncio
async def test_trigger_task_updates_parent_state_and_run_history(app_and_client):
    """Verify manual trigger updates last_run_at, last_status, and inserts a row in runs."""
    client, session_factory, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/scheduler/tasks/heartbeat_health_check/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    # Query DB directly to verify persistence
    async with session_factory() as session:
        task_repo = SchedulerTaskRepository(session)
        task = await task_repo.get("heartbeat_health_check")
        assert task.last_status == "SUCCESS"
        assert task.last_run_at is not None

        runs = await task_repo.get_recent_runs("heartbeat_health_check", limit=5)
        assert len(runs) >= 1


@pytest.mark.asyncio
async def test_cron_to_human_interval_mappings():
    """Verify precision of cron_to_human_interval helper across standard bot patterns."""
    assert cron_to_human_interval("*/15 * * * *")[0] == 15
    assert cron_to_human_interval("0 * * * *")[0] == 1
    assert cron_to_human_interval("0 * * * *")[1] == "HOURS"
    assert cron_to_human_interval("0 0 * * *")[1] == "DAYS"
    assert cron_to_human_interval("0 0 * * 0")[1] == "WEEKS"
    assert cron_to_human_interval("0 0 1 * *")[1] == "MONTHS"


# =============================================================================
# 5. SECURITY CASES
# =============================================================================
@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(app_and_client):
    """Requests without Bearer token must return 401 Unauthorized."""
    client, _, _ = app_and_client

    # GET list
    res = await client.get("/api/v1/scheduler/tasks")
    assert res.status_code == 401

    # GET detail
    res = await client.get("/api/v1/scheduler/tasks/daily_risk_snapshot")
    assert res.status_code == 401

    # PATCH
    res = await client.patch("/api/v1/scheduler/tasks/daily_risk_snapshot", json={"is_active": False})
    assert res.status_code == 401

    # POST trigger
    res = await client.post("/api/v1/scheduler/tasks/daily_risk_snapshot/trigger")
    assert res.status_code == 401

    # POST recovery
    res = await client.post("/api/v1/scheduler/recovery")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_viewer_forbidden_on_mutations(app_and_client):
    """User with VIEWER role must receive 403 Forbidden on mutation and execution endpoints."""
    client, _, _ = app_and_client
    token = await get_viewer_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. PATCH is forbidden
    res = await client.patch("/api/v1/scheduler/tasks/daily_risk_snapshot", headers=headers, json={"is_active": False})
    assert res.status_code == 403
    assert "admin" in res.json()["detail"].lower()

    # 2. Trigger is forbidden
    res = await client.post("/api/v1/scheduler/tasks/daily_risk_snapshot/trigger", headers=headers)
    assert res.status_code == 403

    # 3. Recovery is forbidden
    res = await client.post("/api/v1/scheduler/recovery", headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_viewer_allowed_on_reads(app_and_client):
    """User with VIEWER role is permitted to read tasks, details, and runs."""
    client, _, _ = app_and_client
    token = await get_viewer_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET list allowed
    res1 = await client.get("/api/v1/scheduler/tasks", headers=headers)
    assert res1.status_code == 200

    # 2. GET detail allowed
    res2 = await client.get("/api/v1/scheduler/tasks/daily_risk_snapshot", headers=headers)
    assert res2.status_code == 200

    # 3. GET runs allowed
    res3 = await client.get("/api/v1/scheduler/tasks/daily_risk_snapshot/runs", headers=headers)
    assert res3.status_code == 200
