"""Negative test cases: Binance Exchange & Telegram API failure scenarios."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, Strategy, SignalProvider, RiskProfile, DailyRiskConfig
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
from src.domain.entities.signal import ParsedSignalDTO
from src.domain.exceptions.exchange import (
    ExchangeError,
    ExchangeAuthError,
    InsufficientMarginError,
    OrderRejectError,
    RateLimitError,
)
from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramSendError,
    TelegramMessageParseError,
)
from src.domain.exceptions.trade import TradeExecutionError
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.services.trade_service import TradeService
from src.services.risk_calculator import RiskCalculatorService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient
from src.utils.error_parser import ErrorParser

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


@pytest_asyncio.fixture
async def seeded_env(async_session: AsyncSession):
    """Seed base exchange, account, instrument, watchlist, and strategy."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    strat_repo = StrategyRepository(async_session)
    sig_prov_repo = SignalProviderRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="TESTNET",
        is_active=True,
    ))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"),
        price_precision=2,
        qty_precision=3,
        min_notional=Decimal("5.0"),
        max_leverage=125,
        is_active=True,
    ))
    await watch_repo.create(WatchlistCreate(instrument_id=instrument.id, is_active=True))
    strategy = await strat_repo.create(StrategyCreate(name="DefaultStrategy", is_active=True))
    provider = await sig_prov_repo.create(SignalProviderCreate(name="CryptoVIP", channel_id="123456", is_active=True))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": instrument,
        "strategy": strategy,
        "provider": provider,
    }


# =============================================================================
# 1. BINANCE EXCHANGE API NEGATIVE CASES
# =============================================================================

@pytest.mark.asyncio
async def test_binance_insufficient_margin_error(async_session: AsyncSession, seeded_env: dict):
    """Test handling of Binance API error -2019 (Margin is insufficient)."""
    env = seeded_env
    mock_binance = BinanceRestClient()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_positions = AsyncMock(return_value=[])
    mock_binance.set_leverage = AsyncMock(return_value={"symbol": "BTCUSDT", "leverage": 10})
    mock_binance.set_margin_mode = AsyncMock(return_value={"symbol": "BTCUSDT", "margin_mode": "ISOLATED"})
    # Simulate insufficient margin on entry order
    mock_binance.create_entry_order = AsyncMock(
        side_effect=InsufficientMarginError("Margin is insufficient to open position", details={"code": -2019})
    )

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorService(),
        binance_client=mock_binance,
    )

    signal = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("50000"),
        entry_max=Decimal("50000"),
        sl_price=Decimal("48000"),
        tp_targets=[Decimal("54000")],
        leverage=10,
        raw_text="BUY BTCUSDT",
    )

    with pytest.raises((TradeExecutionError, InsufficientMarginError)) as exc_info:
        await trade_service.execute_signal(
            signal_dto=signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )

    assert "Margin is insufficient" in str(exc_info.value)


@pytest.mark.asyncio
async def test_binance_auth_error_bad_api_key(async_session: AsyncSession, seeded_env: dict):
    """Test handling of Binance API error -2015 (Invalid API Key or IP not whitelisted)."""
    env = seeded_env
    mock_binance = BinanceRestClient()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_positions = AsyncMock(return_value=[])
    mock_binance.set_leverage = AsyncMock(return_value={"symbol": "BTCUSDT", "leverage": 10})
    mock_binance.set_margin_mode = AsyncMock(return_value={"symbol": "BTCUSDT", "margin_mode": "ISOLATED"})
    mock_binance.create_entry_order = AsyncMock(
        side_effect=ExchangeAuthError("Invalid API-key, IP, or permissions for action", details={"code": -2015})
    )

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorService(),
        binance_client=mock_binance,
    )

    signal = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("50000"),
        entry_max=Decimal("50000"),
        sl_price=Decimal("48000"),
        tp_targets=[Decimal("54000")],
        leverage=10,
        raw_text="BUY BTCUSDT",
    )

    with pytest.raises((TradeExecutionError, ExchangeAuthError)) as exc_info:
        await trade_service.execute_signal(
            signal_dto=signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )

    assert "Invalid API-key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_binance_rate_limit_error(async_session: AsyncSession, seeded_env: dict):
    """Test handling of Binance API error -1003 (Rate limit exceeded)."""
    env = seeded_env
    mock_binance = BinanceRestClient()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_positions = AsyncMock(return_value=[])
    mock_binance.set_leverage = AsyncMock(
        side_effect=RateLimitError("Too many requests; IP banned until timestamp", details={"code": -1003})
    )
    mock_binance.set_margin_mode = AsyncMock(return_value={"symbol": "BTCUSDT", "margin_mode": "ISOLATED"})

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorService(),
        binance_client=mock_binance,
    )

    signal = ParsedSignalDTO(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("50000"),
        entry_max=Decimal("50000"),
        sl_price=Decimal("48000"),
        tp_targets=[Decimal("54000")],
        leverage=10,
        raw_text="BUY BTCUSDT",
    )

    with pytest.raises((TradeExecutionError, RateLimitError)) as exc_info:
        await trade_service.execute_signal(
            signal_dto=signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )

    assert "Too many requests" in str(exc_info.value)


# =============================================================================
# 2. TELEGRAM API NEGATIVE CASES
# =============================================================================

@pytest.mark.asyncio
async def test_telegram_rate_limit_429():
    """Test TelegramNotifierClient handling HTTP 429 Rate Limit with retry_after parameter."""
    client = TelegramNotifierClient(bot_token="test_token")
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests: retry after 45",
        "parameters": {"retry_after": 45},
    }

    with pytest.raises(TelegramRateLimitError) as exc_info:
        client._handle_response_error(mock_response, "sendMessage")

    assert exc_info.value.retry_after == 45
    assert "Too Many Requests" in str(exc_info.value)


@pytest.mark.asyncio
async def test_telegram_forbidden_403_bot_blocked():
    """Test TelegramNotifierClient handling HTTP 403 Forbidden (Bot blocked by user)."""
    client = TelegramNotifierClient(bot_token="test_token")
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.json.return_value = {
        "ok": False,
        "error_code": 403,
        "description": "Forbidden: bot was blocked by the user",
    }

    with pytest.raises(TelegramSendError) as exc_info:
        client._handle_response_error(mock_response, "sendMessage")

    assert "Forbidden" in str(exc_info.value)


@pytest.mark.asyncio
async def test_telegram_parse_error_400_bad_markdown():
    """Test TelegramNotifierClient handling HTTP 400 entity parse error."""
    client = TelegramNotifierClient(bot_token="test_token")
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: can't parse entities in message text",
    }

    with pytest.raises(TelegramMessageParseError) as exc_info:
        client._handle_response_error(mock_response, "sendMessage")

    assert "Parse error" in str(exc_info.value)


# =============================================================================
# 3. ERROR PARSER CATEGORIZATION VERIFICATION
# =============================================================================

def test_error_parser_categorization_and_formatting():
    """Test ErrorParser converting various domain and exchange exceptions into user-friendly alerts."""
    # 1. Balance category
    err_balance = ErrorParser.parse_error(InsufficientMarginError("Margin -2019"))
    assert err_balance.category == "BALANCE"
    assert "INSUFFICIENT" in err_balance.title.upper()

    # 2. Risk category
    err_risk = ErrorParser.parse(TradeExecutionError("Min notional requirement not met"))
    assert err_risk.category in ("RISK", "SYSTEM", "EXCHANGE")

    # 3. Formatted Telegram markdown
    md = err_balance.to_telegram_markdown(symbol="BTCUSDT", side="BUY")
    assert "BTCUSDT" in md
    assert "Suggested Action" in md
