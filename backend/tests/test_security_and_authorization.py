"""Security and Safety test cases: API key masking, emergency panic close all, and leverage clamping."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, Trade, Order, Execution, TradeEvent, TradeSummary, TradingCredential
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, TradingCredentialCreate, TradingCredentialRead
from src.schemas.trade import TradeCreate
from src.schemas.order import OrderCreate
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.services.position_manager import PositionManager
from src.services.precision_filter import PrecisionFilterService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create in-memory SQLite database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


# =============================================================================
# 1. CREDENTIAL MASKING & LEAK PREVENTION
# =============================================================================

@pytest.mark.asyncio
async def test_credential_masking_in_api_responses(async_session: AsyncSession):
    """Test that API responses mask API keys and never expose secret keys."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="TESTNET",
        is_active=True,
    ))

    # Create credential with sensitive keys
    raw_api_key = "abcdefgh12345678"
    raw_secret_key = "secret_xyz_never_leak_this_key"

    cred = await cred_repo.create(TradingCredentialCreate(
        account_id=account.id,
        key_name="Binance Futures Live Key",
        api_key=raw_api_key,
        secret_key=raw_secret_key,
        is_active=True,
    ))

    # Convert to safe Read DTO
    safe_dto = TradingCredentialRead.from_orm_model(cred)

    # 1. API key must be masked
    assert safe_dto.masked_api_key == "abcd****5678"
    assert raw_api_key not in (safe_dto.masked_api_key or "")

    # 2. Secret key must NOT exist in schema fields
    schema_dump = safe_dto.model_dump()
    assert "secret_key" not in schema_dump
    assert "encrypted_secret_key" not in schema_dump
    assert raw_secret_key not in str(schema_dump)


# =============================================================================
# 2. EMERGENCY PANIC BUTTON (CLOSE ALL POSITIONS & CANCEL ALL ORDERS)
# =============================================================================

@pytest.mark.asyncio
async def test_emergency_panic_close_all_positions(async_session: AsyncSession):
    """Test emergency panic button market-closes all active trades and cancels all open orders."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id, name="Main Account", environment="TESTNET", is_active=True
    ))
    btc_inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), max_qty=Decimal("100"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), max_leverage=125, is_active=True
    ))

    # Active Trade 1 (BTCUSDT)
    trade1 = await trade_repo.create(TradeCreate(
        account_id=account.id, instrument_id=btc_inst.id, side="BUY", status="OPEN",
        entry_price=Decimal("50000"), avg_entry_price=Decimal("50000"), sl_price=Decimal("48000"),
        leverage=10, position_size=Decimal("0.02"), remaining_qty=Decimal("0.02"),
    ))
    ord1 = await order_repo.create(OrderCreate(
        trade_id=trade1.id, exchange_order_id="ORD_TP_1", purpose="TP1", order_type="LIMIT",
        side="SELL", price=Decimal("52000"), qty=Decimal("0.01"), status="NEW",
    ))

    mock_binance = BinanceRestClient()
    mock_binance.cancel_all_orders = AsyncMock(return_value=[{"id": "ORD_TP_1", "status": "CANCELED"}])
    mock_binance.create_entry_order = AsyncMock(return_value={"id": "PANIC_CLOSE_1", "status": "FILLED", "average": 49500.0})
    mock_tg = AsyncMock(spec=TelegramNotifierClient)

    pos_mgr = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        binance_client=mock_binance,
        telegram_client=mock_tg,
    )

    # Trigger panic close
    result = await pos_mgr.close_position_market(trade_id=trade1.id, reason="PANIC_EMERGENCY")

    assert result is True
    updated_trade = await trade_repo.get(trade1.id)
    assert updated_trade.status == "CLOSED"
    assert updated_trade.remaining_qty == Decimal("0")

    # Verify Binance cancel_all_orders was executed
    mock_binance.cancel_all_orders.assert_awaited()


# =============================================================================
# 3. LEVERAGE CLAMPING SECURITY GUARD
# =============================================================================

def test_leverage_clamping_to_exchange_max():
    """Verify that excessive leverage requested in signals is safely clamped."""
    # Sinyal meminta 100x pada aset dengan batas instrumen 20x
    clamped_lev = PrecisionFilterService.clamp_leverage(requested_leverage=100, max_leverage=20, min_leverage=1)
    assert clamped_lev == 20

    # Sinyal meminta 0x atau negatif
    clamped_zero = PrecisionFilterService.clamp_leverage(requested_leverage=0, max_leverage=50, min_leverage=1)
    assert clamped_zero == 1
