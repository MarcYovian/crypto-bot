"""Comprehensive API test suite for System Audit Logs and CSV Reports Export."""

import pytest
import pytest_asyncio
import csv
import io
import json
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from sqlalchemy.pool import StaticPool

from src.database.connection import Base
from src.database.models import (
    Exchange,
    TradingAccount,
    Instrument,
    Trade,
    TradeSummary,
    BotLog,
)
from src.repository.user_repository import UserRepository
from src.utils.security import get_password_hash
from src.utils.cache import in_memory_cache
from src.api.app import create_app
from src.api.deps import get_db_session

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    """Create in-memory SQLite database, app instance, and test client."""
    await in_memory_cache.clear()

    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    app = create_app()

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db_session

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

        # 2. Exchange & Trading Account & Instrument
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
        await session.flush()

        inst1 = Instrument(
            id=1,
            exchange_id=1,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.10"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=3,
            is_active=True,
        )
        inst2 = Instrument(
            id=2,
            exchange_id=1,
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.01"),
            min_qty=Decimal("0.01"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=2,
            is_active=True,
        )
        session.add_all([inst1, inst2])
        await session.flush()

        # 3. Seed Audit Logs
        now = datetime.now(timezone.utc)
        logs = [
            BotLog(
                id=1,
                module="EXECUTION_ENGINE",
                level="INFO",
                message="Signal parsed successfully for BTCUSDT sig-trace-101",
                context_json=json.dumps({"trace_id": "sig-trace-101", "symbol": "BTCUSDT"}),
                created_at=now - timedelta(minutes=20),
            ),
            BotLog(
                id=2,
                module="RISK_MANAGER",
                level="WARNING",
                message="High volatility detected on ETHUSDT",
                context_json=json.dumps({"symbol": "ETHUSDT", "volatility": 0.08}),
                created_at=now - timedelta(minutes=15),
            ),
            BotLog(
                id=3,
                module="EXECUTION_ENGINE",
                level="ERROR",
                message="Order placement failed on BTCUSDT with error: Insufficient margin (sig-trace-101)",
                context_json=json.dumps({"trace_id": "sig-trace-101", "error": "InsufficientMargin"}),
                created_at=now - timedelta(minutes=10),
            ),
            BotLog(
                id=4,
                module="SCHEDULER",
                level="INFO",
                message="Periodic healthcheck completed normally",
                context_json=None,
                created_at=now - timedelta(minutes=5),
            ),
            BotLog(
                id=5,
                module="TELEGRAM_BOT",
                level="DEBUG",
                message="Incoming webhook update processed",
                context_json=json.dumps({"update_id": 98765}),
                created_at=now - timedelta(minutes=2),
            ),
            BotLog(
                id=6,
                module="CIRCUIT_BREAKER",
                level="CRITICAL",
                message="Emergency circuit breaker tripped for daily loss violation",
                context_json=json.dumps({"daily_loss_pct": 6.5}),
                created_at=now - timedelta(minutes=1),
            ),
        ]
        session.add_all(logs)

        # 4. Seed Closed Trades & Summaries
        t1 = Trade(
            id=101,
            account_id=1,
            instrument_id=1,
            side="BUY",
            entry_price=Decimal("50000.0"),
            sl_price=Decimal("49000.0"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0"),
            leverage=20,
            status="CLOSED",
            created_at=now - timedelta(days=2),
            closed_at=now - timedelta(days=2, hours=-1),
        )
        s1 = TradeSummary(
            trade_id=101,
            gross_pnl=Decimal("200.00"),
            commission=Decimal("5.00"),
            net_pnl=Decimal("195.00"),
            roi=Decimal("7.80"),
            rr=Decimal("2.5"),
            duration_seconds=3600,
            result="WIN",
            close_reason="TP2",
            closed_at=now - timedelta(days=2, hours=-1),
        )

        t2 = Trade(
            id=102,
            account_id=1,
            instrument_id=2,
            side="SELL",
            entry_price=Decimal("3000.0"),
            sl_price=Decimal("3100.0"),
            position_size=Decimal("1.0"),
            remaining_qty=Decimal("0"),
            leverage=10,
            status="CLOSED",
            created_at=now - timedelta(days=5),
            closed_at=now - timedelta(days=5, hours=-2),
        )
        s2 = TradeSummary(
            trade_id=102,
            gross_pnl=Decimal("-100.00"),
            commission=Decimal("3.00"),
            net_pnl=Decimal("-103.00"),
            roi=Decimal("-3.43"),
            rr=Decimal("-1.0"),
            duration_seconds=7200,
            result="LOSS",
            close_reason="SL",
            closed_at=now - timedelta(days=5, hours=-2),
        )

        session.add_all([t1, s1, t2, s2])
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory

    await engine.dispose()



async def get_token(client: AsyncClient, username: str = "admin", password: str = "AdminPass123!") -> str:
    """Helper to login and retrieve access token."""
    res = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_get_logs_all_recent(app_and_client):
    """Test querying recent logs returns sorted log entries with metadata."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 6
    # Check descending order
    assert data[0]["id"] == 6
    assert data[0]["level"] == "CRITICAL"
    assert data[0]["module"] == "CIRCUIT_BREAKER"


@pytest.mark.asyncio
async def test_get_logs_filtered_by_level(app_and_client):
    """Test filtering logs by level."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/logs?level=ERROR",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["level"] == "ERROR"
    assert data[0]["id"] == 3


@pytest.mark.asyncio
async def test_get_logs_filtered_by_trace_id(app_and_client):
    """Test correlation search using trace_id in logs."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/logs?trace_id=sig-trace-101",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    for entry in data:
        assert entry["trace_id"] == "sig-trace-101"


@pytest.mark.asyncio
async def test_get_logs_pagination_limit(app_and_client):
    """Test pagination limit parameter."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/logs?limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_export_trades_csv_success(app_and_client):
    """Test CSV report generation and export format."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/reports/export/csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    assert 'filename="trades_report.csv"' in res.headers.get("content-disposition", "")

    content = res.text
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    # Check Header
    assert len(rows) >= 3  # Header + 2 rows
    assert rows[0] == [
        "Trade ID",
        "Symbol",
        "Side",
        "Entry Price",
        "Exit Price",
        "Position Size",
        "Leverage",
        "Gross PnL (USDT)",
        "Commission (USDT)",
        "Net PnL (USDT)",
        "ROI %",
        "Result",
        "Close Reason",
        "Opened At",
        "Closed At",
    ]

    # Verify Trade 101 data
    t1_row = next(r for r in rows if r[0] == "101")
    assert t1_row[1] == "BTCUSDT"
    assert t1_row[2] == "BUY"
    assert t1_row[7] == "200.00"
    assert t1_row[9] == "195.00"
    assert t1_row[11] == "WIN"
    assert t1_row[12] == "TP2"


@pytest.mark.asyncio
async def test_export_trades_csv_date_filter(app_and_client):
    """Test CSV report generation with date range filtering."""
    client, _ = app_and_client
    token = await get_token(client)

    # Filter for trades closed within last 3 days (only Trade 101, since Trade 102 was 5 days ago)
    today = date.today()
    start = (today - timedelta(days=3)).isoformat()
    end = today.isoformat()

    res = await client.get(
        f"/api/v1/reports/export/csv?start_date={start}&end_date={end}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    rows = list(csv.reader(io.StringIO(res.text)))
    assert len(rows) == 2  # Header + 1 trade
    assert rows[1][0] == "101"


@pytest.mark.asyncio
async def test_export_trades_csv_empty_dataset(app_and_client):
    """Test CSV export when no trades match the given period."""
    client, _ = app_and_client
    token = await get_token(client)

    start = "2020-01-01"
    end = "2020-01-31"

    res = await client.get(
        f"/api/v1/reports/export/csv?start_date={start}&end_date={end}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    rows = list(csv.reader(io.StringIO(res.text)))
    assert len(rows) == 1  # Only header


@pytest.mark.asyncio
async def test_export_trades_csv_invalid_date_range(app_and_client):
    """Test that start_date > end_date returns 400 Bad Request."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/reports/export/csv?start_date=2026-08-30&end_date=2026-08-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "start_date" in res.json()["detail"]


@pytest.mark.asyncio
async def test_get_logs_invalid_level(app_and_client):
    """Test that invalid log level returns 400 Bad Request."""
    client, _ = app_and_client
    token = await get_token(client)

    res = await client.get(
        "/api/v1/logs?level=SUPER_FATAL",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "Invalid log level" in res.json()["detail"]


@pytest.mark.asyncio
async def test_logs_unauthorized_rejection(app_and_client):
    """Test that unauthenticated request to /logs is rejected with 401."""
    client, _ = app_and_client
    res = await client.get("/api/v1/logs")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_reports_unauthorized_rejection(app_and_client):
    """Test that unauthenticated request to /reports/export/csv is rejected with 401."""
    client, _ = app_and_client
    res = await client.get("/api/v1/reports/export/csv")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_logs_and_reports_accessible_by_viewer_and_admin(app_and_client):
    """Test that both VIEWER and ADMIN roles can access logs and export reports."""
    client, _ = app_and_client
    viewer_token = await get_token(client, username="viewer", password="ViewerPass123!")

    res_logs = await client.get(
        "/api/v1/logs",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_logs.status_code == 200

    res_reports = await client.get(
        "/api/v1/reports/export/csv",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_reports.status_code == 200
