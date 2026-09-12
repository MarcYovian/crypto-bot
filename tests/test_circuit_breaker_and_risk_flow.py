"""Unit and integration tests for daily risk calculations, circuit breaker protection, and Telegram command flows."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.application.dto.risk_commands import CheckDailyRiskCommand
from src.application.dto.trade_commands import ExecuteSignalCommand
from src.presentation.api.schemas.signal import ParsedSignalDTO
from src.presentation.api.schemas.master import (
    ExchangeCreate,
    TradingAccountCreate,
    RiskProfileCreate,
    InstrumentCreate,
)
from src.presentation.api.schemas.risk import DailyRiskConfigCreate, TradeRiskCreate
from src.application.use_cases.risk.check_daily_risk_use_case import CheckDailyRiskUseCase
from src.application.use_cases.risk.daily_risk_snapshot_use_case import DailyRiskSnapshotUseCase
from src.application.use_cases.telegram.handle_command_use_case import HandleTelegramCommandUseCase
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.domain.exceptions.trade import DailyRiskLimitReachedError
from src.infrastructure.persistence.models import (
    DailyRiskConfig,
    Instrument,
    RiskProfile,
    Trade,
    TradeRisk,
    TradingAccount,
    Watchlist,
)
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository

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


@pytest_asyncio.fixture
async def base_entities(async_session: AsyncSession):
    """Seed prerequisite master entities (Exchange, Account, RiskProfile, Instrument)."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    rp_repo = RiskProfileRepository(async_session)
    inst_repo = InstrumentRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Futures Account",
        account_type="FUTURES",
        environment="MAINNET",
        is_active=True
    ))
    profile = await rp_repo.create(RiskProfileCreate(
        name="Strict 2% Profile",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("5.0"),
        max_open_trade=3,
        is_active=True
    ))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True
    ))
    return {"exchange": exchange, "account": account, "profile": profile, "instrument": instrument}


# =============================================================================
# 1. REPOSITORY LEVEL UNIT TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_daily_risk_repository_budget_and_margin_calculations(async_session: AsyncSession, base_entities: dict):
    """Test DailyRiskRepository remaining budget calculation based on daily_risk_amount."""
    daily_repo = DailyRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]
    inst = base_entities["instrument"]

    # 1. Create a snapshot: Balance = $10,000, 2% risk/trade = $200, 5% daily loss limit = $500
    snapshot = await daily_repo.create(
        DailyRiskConfigCreate(
            account_id=acc.id,
            risk_profile_id=prof.id,
            date=date.today(),
            balance=Decimal("10000.0"),
            risk_amount=Decimal("200.0"),
            daily_risk_amount=Decimal("500.0"),
        )
    )
    assert snapshot.id is not None
    assert snapshot.risk_amount == Decimal("200.0")
    assert snapshot.daily_risk_amount == Decimal("500.0")

    # Initially with 0 active trades, remaining budget must equal daily_risk_amount ($500)
    initial_rem = await daily_repo.get_remaining_risk_budget(snapshot.id)
    assert initial_rem == Decimal("500.0")

    initial_margin = await daily_repo.get_total_margin_used(snapshot.id)
    assert initial_margin == Decimal("0.0")

    # 2. Add an active trade with allocated risk = $200, margin = $500
    trade = Trade(
        account_id=acc.id,
        instrument_id=inst.id,
        strategy_id=1,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("48000.0"),
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
        leverage=20,
    )
    async_session.add(trade)
    await async_session.commit()
    await async_session.refresh(trade)

    t_risk = TradeRisk(
        trade_id=trade.id,
        daily_risk_id=snapshot.id,
        entry=Decimal("50000.0"),
        stop=Decimal("48000.0"),
        stop_distance=Decimal("2000.0"),
        qty=Decimal("0.1"),
        margin=Decimal("500.0"),
        risk_amount=Decimal("200.0"),
        leverage=20,
    )
    async_session.add(t_risk)
    await async_session.commit()

    # Remaining budget should be $500 - $200 = $300
    rem_after_1 = await daily_repo.get_remaining_risk_budget(snapshot.id)
    assert rem_after_1 == Decimal("300.0")

    margin_used = await daily_repo.get_total_margin_used(snapshot.id)
    assert margin_used == Decimal("500.0")

    # 3. Add second trade with risk = $200, margin = $500
    trade2 = Trade(
        account_id=acc.id,
        instrument_id=inst.id,
        strategy_id=1,
        side="SELL",
        status="WAITING_ENTRY",
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("52000.0"),
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
        leverage=20,
    )
    async_session.add(trade2)
    await async_session.commit()
    await async_session.refresh(trade2)

    t_risk2 = TradeRisk(
        trade_id=trade2.id,
        daily_risk_id=snapshot.id,
        entry=Decimal("50000.0"),
        stop=Decimal("52000.0"),
        stop_distance=Decimal("2000.0"),
        qty=Decimal("0.1"),
        margin=Decimal("500.0"),
        risk_amount=Decimal("200.0"),
        leverage=20,
    )
    async_session.add(t_risk2)
    await async_session.commit()

    # Remaining budget should be $500 - $400 = $100
    rem_after_2 = await daily_repo.get_remaining_risk_budget(snapshot.id)
    assert rem_after_2 == Decimal("100.0")

    # 4. Closed trade should release risk budget
    trade2.status = "CLOSED"
    async_session.add(trade2)
    await async_session.commit()

    rem_after_close = await daily_repo.get_remaining_risk_budget(snapshot.id)
    assert rem_after_close == Decimal("300.0")


# =============================================================================
# 2. USE CASE: CheckDailyRiskUseCase
# =============================================================================

@pytest.mark.asyncio
async def test_check_daily_risk_use_case_edge_cases():
    """Test CheckDailyRiskUseCase status and reasons under normal and breached conditions."""
    daily_risk_repo = MagicMock(spec=DailyRiskRepository)
    risk_profile_repo = MagicMock(spec=RiskProfileRepository)
    trade_repo = MagicMock(spec=TradeRepository)

    use_case = CheckDailyRiskUseCase(
        daily_risk_repo=daily_risk_repo,
        risk_profile_repo=risk_profile_repo,
        trade_repo=trade_repo,
    )

    mock_profile = MagicMock(max_open_trade=3)
    risk_profile_repo.get_or_create_default_profile = AsyncMock(return_value=mock_profile)
    trade_repo.get_all_active_trades = AsyncMock(return_value=[])

    # Case A: Normal status (remaining budget $300 > trade risk $200)
    mock_snapshot = MagicMock(
        id=1,
        balance=Decimal("10000.0"),
        risk_amount=Decimal("200.0"),
        daily_risk_amount=Decimal("500.0"),
    )
    daily_risk_repo.get_by_date = AsyncMock(return_value=mock_snapshot)
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("300.0"))

    res_normal = await use_case.execute(CheckDailyRiskCommand(account_id=1))
    assert res_normal["is_circuit_breaker_active"] is False
    assert res_normal["daily_risk_amount"] == 500.0
    assert res_normal["per_trade_risk_amount"] == 200.0
    assert res_normal["remaining_risk_budget"] == 300.0
    assert res_normal["reason"] == "OK"

    # Case B: Edge case - remaining budget ($150) is less than per-trade risk ($200)
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("150.0"))
    res_insufficient = await use_case.execute(CheckDailyRiskCommand(account_id=1))
    assert res_insufficient["is_circuit_breaker_active"] is True
    assert res_insufficient["reason"] == "PER_TRADE_RISK_EXCEEDS_BUDGET"

    # Case C: Edge case - remaining budget is 0 or negative
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("0.0"))
    res_zero = await use_case.execute(CheckDailyRiskCommand(account_id=1))
    assert res_zero["is_circuit_breaker_active"] is True
    assert res_zero["reason"] == "DAILY_RISK_LIMIT_REACHED"


# =============================================================================
# 3. USE CASE: ExecuteSignalUseCase Risk Validation
# =============================================================================

@pytest.mark.asyncio
async def test_execute_signal_rejects_when_trade_risk_exceeds_remaining_budget():
    """Test that ExecuteSignalUseCase raises DailyRiskLimitReachedError when trade risk > remaining budget."""
    instrument_repo = MagicMock(spec=InstrumentRepository)
    watchlist_repo = MagicMock(spec=WatchlistRepository)
    trade_repo = MagicMock(spec=TradeRepository)
    trade_risk_repo = MagicMock(spec=TradeRiskRepository)
    daily_risk_repo = MagicMock(spec=DailyRiskRepository)
    order_repo = MagicMock(spec=OrderRepository)
    trade_event_repo = MagicMock(spec=TradeEventRepository)
    risk_profile_repo = MagicMock(spec=RiskProfileRepository)
    exchange_gateway = MagicMock()
    event_publisher = MagicMock()

    instrument_repo.get_by_symbol = AsyncMock(return_value=MagicMock(id=1, tick_size=Decimal("0.1"), price_precision=2))
    watchlist_repo.is_symbol_enabled = AsyncMock(return_value=True)
    trade_repo.get_active_trade_by_instrument = AsyncMock(return_value=None)
    trade_repo.get_all_active_trades = AsyncMock(return_value=[])

    risk_profile_repo.get_or_create_default_profile = AsyncMock(
        return_value=MagicMock(id=1, max_open_trade=3, risk_percent=Decimal("2.0"), max_daily_loss=Decimal("5.0"))
    )

    exchange_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("10000.0")})
    exchange_gateway.fetch_ticker = AsyncMock(return_value={"last_price": Decimal("60000.0")})

    # Snapshot configured: Per-trade risk = $200, Daily risk budget = $500
    mock_snapshot = MagicMock(id=1, balance=Decimal("10000.0"), risk_amount=Decimal("200.0"), daily_risk_amount=Decimal("500.0"))
    daily_risk_repo.get_by_date = AsyncMock(return_value=mock_snapshot)

    # Remaining budget is only $100 (less than $200 trade risk)
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("100.0"))

    use_case = ExecuteSignalUseCase(
        instrument_repo=instrument_repo,
        watchlist_repo=watchlist_repo,
        trade_repo=trade_repo,
        trade_risk_repo=trade_risk_repo,
        daily_risk_repo=daily_risk_repo,
        order_repo=order_repo,
        trade_event_repo=trade_event_repo,
        risk_profile_repo=risk_profile_repo,
        exchange_gateway=exchange_gateway,
        event_publisher=event_publisher,
    )

    sig = ParsedSignalDTO(
        raw_text="BUY BTCUSDT",
        symbol="BTCUSDT",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp_targets=[Decimal("64000.0")],
        is_valid=True,
    )

    with pytest.raises(DailyRiskLimitReachedError) as exc_info:
        await use_case.execute(ExecuteSignalCommand(signal_dto=sig))

    assert "Daily risk limit breached" in str(exc_info.value)
    assert "Required trade risk (200.00 USDT) exceeds remaining daily budget (100.00 USDT)" in str(exc_info.value)


# =============================================================================
# 4. TELEGRAM COMMAND /circuit_breaker & /risk
# =============================================================================

@pytest.mark.asyncio
async def test_telegram_circuit_breaker_command_formatting_and_edge_cases():
    """Test /circuit_breaker Telegram handler responses for normal, breached, and on-demand fallback flows."""
    daily_risk_repo = MagicMock(spec=DailyRiskRepository)
    risk_profile_repo = MagicMock(spec=RiskProfileRepository)
    exchange_gateway = MagicMock()

    use_case = HandleTelegramCommandUseCase(
        trade_repo=MagicMock(),
        order_repo=MagicMock(),
        trade_summary_repo=MagicMock(),
        daily_risk_repo=daily_risk_repo,
        watchlist_repo=MagicMock(),
        bot_log_repo=MagicMock(),
        bot_setting_repo=MagicMock(),
        trading_account_repo=MagicMock(),
        trading_credential_repo=MagicMock(),
        instrument_repo=MagicMock(),
        risk_profile_repo=risk_profile_repo,
        close_trade_use_case=MagicMock(),
        exchange_gateway=exchange_gateway,
        notification_gateway=MagicMock(),
    )

    # 1. Normal State Test
    mock_snapshot_normal = MagicMock(
        id=1,
        balance=Decimal("10000.0"),
        risk_amount=Decimal("200.0"),
        daily_risk_amount=Decimal("500.0"),
    )
    daily_risk_repo.get_by_date = AsyncMock(return_value=mock_snapshot_normal)
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("300.0"))
    daily_risk_repo.get_total_margin_used = AsyncMock(return_value=Decimal("500.0"))

    res_normal = await use_case.execute_command("/circuit_breaker")
    assert "STATUS CIRCUIT BREAKER & RISK" in res_normal
    assert "Status Proteksi: <b>🟢 NORMAL</b>" in res_normal
    assert "Modal Awal Hari: <b>$10,000.00 USDT</b>" in res_normal
    assert "Batas Risiko Harian: <b>$500.00 USDT</b>" in res_normal
    assert "Batas Risiko Per Trade: <b>$200.00 USDT</b>" in res_normal
    assert "Sisa Anggaran Risiko: <b>$300.00 USDT</b>" in res_normal
    assert "Margin Digunakan: <b>$500.00 USDT</b>" in res_normal

    # 2. Alias /risk Test
    res_alias = await use_case.execute_command("/risk")
    assert res_alias == res_normal

    # 3. Breached / Locked State Test
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("0.0"))
    res_breached = await use_case.execute_command("/circuit_breaker")
    assert "Status Proteksi: <b>🔴 BREACHED / LOCKED</b>" in res_breached
    assert "Sisa Anggaran Risiko: <b>$0.00 USDT</b>" in res_breached

    # 4. Fallback on-demand snapshot creation when no snapshot exists
    daily_risk_repo.get_by_date = AsyncMock(return_value=None)
    daily_risk_repo.get_latest_snapshot = AsyncMock(return_value=None)
    exchange_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("20000.0")})
    risk_profile_repo.get_active_profile = AsyncMock(
        return_value=MagicMock(risk_percent=Decimal("2.0"), max_daily_loss=Decimal("6.0"))
    )

    created_snap = MagicMock(
        id=2,
        balance=Decimal("20000.0"),
        risk_amount=Decimal("400.0"),
        daily_risk_amount=Decimal("1200.0"),
    )
    daily_risk_repo.get_or_create_daily_snapshot = AsyncMock(return_value=created_snap)
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("1200.0"))
    daily_risk_repo.get_total_margin_used = AsyncMock(return_value=Decimal("0.0"))

    res_fallback = await use_case.execute_command("/circuit_breaker")
    assert "Modal Awal Hari: <b>$20,000.00 USDT</b>" in res_fallback
    assert "Batas Risiko Harian: <b>$1,200.00 USDT</b>" in res_fallback
    assert "Batas Risiko Per Trade: <b>$400.00 USDT</b>" in res_fallback
    assert "Sisa Anggaran Risiko: <b>$1,200.00 USDT</b>" in res_fallback
