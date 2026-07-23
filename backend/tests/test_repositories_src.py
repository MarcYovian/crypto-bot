import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.services.signal_parser import ParsedSignal
from src.services.risk_calculator import RiskCalculationResult
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository

# Database SQLite in-memory khusus pengujian unit
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_signal_repository_crud(async_session: AsyncSession):
    repo = SignalRepository(async_session)

    # 1. Simpan Signal
    parsed = ParsedSignal(
        symbol="BTCUSDT",
        side="BUY",
        entry_min=60000.0,
        entry_max=60500.0,
        sl_price=59000.0,
        tp_prices=[62000.0, 64000.0],
        confidence=0.85,
        is_valid=True
    )
    signal = await repo.create_signal_from_parsed(parsed, telegram_message_id=123)

    assert signal.id is not None
    assert signal.symbol == "BTCUSDT"
    assert signal.confirmation_status == "NOT_REQUIRED"
    assert signal.status == "RECEIVED"

    # 2. Duplicate Active Signal Check
    is_dup = await repo.is_duplicate_active_signal("BTCUSDT", "BUY")
    assert is_dup is True

    # 3. Update Status
    await repo.update_signal_status(signal.id, "EXECUTED")
    fetched = await repo.get_by_id(signal.id)
    assert fetched.status == "EXECUTED"


@pytest.mark.asyncio
async def test_trade_repository_lifecycle(async_session: AsyncSession):
    trade_repo = TradeRepository(async_session)

    # 1. Create Daily Risk Snapshot
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_snapshot = await trade_repo.create_daily_risk_snapshot(today_str, balance=1000.0, risk_percent=2.0)
    assert daily_snapshot.risk_amount == 20.0  # 2% dari 1000 USD

    # 2. Create Trade & TradeRisk
    risk_res = RiskCalculationResult(
        is_valid=True,
        risk_amount=20.0,
        entry_price=60000.0,
        stop_loss_price=59000.0,
        stop_distance=1000.0,
        stop_distance_percent=1.66,
        position_size=0.02,
        notional_value=1200.0,
        required_margin=80.0,
        leverage=15
    )

    trade = await trade_repo.create_trade_with_risk(
        signal_id=1,
        symbol="BTCUSDT",
        side="BUY",
        leverage=15,
        risk_date=today_str,
        risk_res=risk_res,
        tp1_price=62000.0
    )

    assert trade.id is not None
    assert trade.position_size == 0.02
    assert trade.status == "WAITING_ENTRY"

    # 3. Create Order
    order = await trade_repo.create_order(
        trade_id=trade.id,
        purpose="ENTRY",
        order_type="LIMIT",
        side="BUY",
        qty=0.02,
        price=60000.0,
        binance_order_id="99887766"
    )
    assert order.id is not None
    assert order.status == "NEW"

    # 4. Record Execution
    exec_record = await trade_repo.record_execution(
        order_id=order.id,
        trade_id=trade.id,
        price=60000.0,
        qty=0.02,
        commission=0.24,
        realized_pnl=0.0
    )
    assert exec_record.id is not None

    # 5. Log Event & Save Summary
    await trade_repo.log_event(trade.id, "ENTRY")
    summary = await trade_repo.save_summary(
        trade_id=trade.id,
        gross_pnl=40.0,
        net_pnl=39.5,
        commission=0.5,
        roi=49.3,
        rr=2.0,
        win=1,
        duration_seconds=3600,
        close_reason="TP1",
        closed_at=datetime.now()
    )
    assert summary.trade_id == trade.id
    assert summary.win == 1
