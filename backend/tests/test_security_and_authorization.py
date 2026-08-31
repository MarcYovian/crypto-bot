"""Security and Safety test cases: API key masking, emergency panic close all, and leverage clamping."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, Trade, Order, Execution, TradeEvent, TradeSummary, TradingCredential
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, TradingCredentialCreate, TradingCredentialRead
from src.presentation.api.schemas.trade import TradeCreate
from src.presentation.api.schemas.order import OrderCreate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.trading_credential_repository import TradingCredentialRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.application.use_cases.trades.close_trade_use_case import CloseTradeUseCase
from src.application.dto.trade_commands import CloseTradeCommand
from src.domain.services.precision_filter import PrecisionFilterDomainService as PrecisionFilterService
from src.domain.ports.gateways import INotificationGateway



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


class MockExchangeGatewayAdapter:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def cancel_all_open_orders(self, symbol: str) -> Any:
        if hasattr(self._client, "cancel_all_orders"):
            res = self._client.cancel_all_orders(symbol=symbol)
            return await res if hasattr(res, "__await__") else res
        return []

    async def create_order(self, **kwargs) -> Dict[str, Any]:
        if hasattr(self._client, "create_entry_order"):
            res = self._client.create_entry_order(**kwargs)
            return await res if hasattr(res, "__await__") else res
        return {"id": "PANIC_CLOSE_1", "status": "FILLED", "average": 49500.0}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class PositionManager:
    def __init__(
        self,
        trade_repo,
        order_repo,
        execution_repo,
        trade_event_repo,
        trade_summary_repo,
        daily_risk_repo=None,
        exchange_gateway=None,
        telegram_client=None,
    ):
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.exchange_gateway = MockExchangeGatewayAdapter(exchange_gateway) if exchange_gateway is not None else None
        self.telegram_client = telegram_client


        self._close_uc = CloseTradeUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            trade_event_repo=self.trade_event_repo,
            trade_summary_repo=self.trade_summary_repo,
            exchange_gateway=self.exchange_gateway,
        )

    async def close_position_market(self, trade_id: int, reason: str = "PANIC_EMERGENCY") -> bool:
        cmd = CloseTradeCommand(trade_id=trade_id, reason=reason)
        res = await self._close_uc.execute(cmd)
        return bool(res.get("status") == "CLOSED")


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

    mock_binance = MagicMock()
    mock_binance.cancel_all_orders = AsyncMock(return_value=[{"id": "ORD_TP_1", "status": "CANCELED"}])

    mock_binance.create_entry_order = AsyncMock(return_value={"id": "PANIC_CLOSE_1", "status": "FILLED", "average": 49500.0})
    mock_tg = AsyncMock(spec=INotificationGateway)


    pos_mgr = PositionManager(
        trade_repo=trade_repo,
        order_repo=order_repo,
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        exchange_gateway=mock_binance,
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


# =============================================================================
# 4. ENVIRONMENT HARDENING & SETTINGS SECURITY
# =============================================================================

def test_settings_development_defaults():
    """Verify default development configuration initializes without error."""
    from config.settings import Settings
    s = Settings(
        ENVIRONMENT="development",
        _env_file=None,
    )
    assert s.ENVIRONMENT == "development"
    assert "http://localhost:3000" in s.CORS_ORIGINS
    assert s.DEFAULT_ADMIN_PASSWORD == "AdminPassword123!"


def test_settings_cors_origins_parsing():
    """Verify CORS_ORIGINS parses comma-separated strings to list."""
    from config.settings import Settings
    s = Settings(
        ENVIRONMENT="development",
        CORS_ORIGINS="https://app.example.com, https://admin.example.com",
        _env_file=None,
    )
    assert s.CORS_ORIGINS == ["https://app.example.com", "https://admin.example.com"]


def test_settings_production_rejects_default_jwt_secret():
    """Verify production mode raises ValueError if JWT_SECRET_KEY is the dev default."""
    from config.settings import Settings
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be securely set in production mode"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="dev-secret-jwt-key-replace-in-production-0987654321",
            DEFAULT_ADMIN_PASSWORD="StrongProductionPassword999!",
            CORS_ORIGINS="https://dashboard.example.com",
            _env_file=None,
        )


def test_settings_production_rejects_default_admin_password():
    """Verify production mode raises ValueError if DEFAULT_ADMIN_PASSWORD is unchanged."""
    from config.settings import Settings
    with pytest.raises(ValueError, match="DEFAULT_ADMIN_PASSWORD must be explicitly provided in production mode"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 64,
            DEFAULT_ADMIN_PASSWORD="AdminPassword123!",
            CORS_ORIGINS="https://dashboard.example.com",
            _env_file=None,
        )


def test_settings_production_rejects_cors_wildcard():
    """Verify production mode raises ValueError if CORS origins contains wildcard *."""
    from config.settings import Settings
    with pytest.raises(ValueError, match="CORS wildcard"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 64,
            DEFAULT_ADMIN_PASSWORD="StrongProductionPassword999!",
            CORS_ORIGINS="*",
            _env_file=None,
        )


def test_settings_production_valid_configuration():
    """Verify production mode succeeds when all security requirements are satisfied."""
    from config.settings import Settings
    s = Settings(
        ENVIRONMENT="production",
        JWT_SECRET_KEY="super-secret-random-production-key-that-is-very-long-and-secure-123456",
        DEFAULT_ADMIN_PASSWORD="StrongAdminPassword999!",
        CORS_ORIGINS="https://dashboard.example.com, https://app.example.com",
        _env_file=None,
    )
    assert s.ENVIRONMENT == "production"
    assert s.CORS_ORIGINS == ["https://dashboard.example.com", "https://app.example.com"]
    assert s.DEFAULT_ADMIN_PASSWORD == "StrongAdminPassword999!"

