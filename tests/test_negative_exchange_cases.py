"""Negative test cases: Binance Exchange & Telegram API failure scenarios."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, Strategy, SignalProvider, RiskProfile, DailyRiskConfig
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
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
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.strategy_repository import StrategyRepository
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.infrastructure.persistence.repositories.signal_repository import SignalRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.dto.trade_commands import ExecuteSignalCommand
from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.infrastructure.gateways.telegram.telegram_connector import TelegramConnector


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


class MockExchangeGatewayAdapter:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def fetch_balance(self, account_id: Optional[int] = None) -> Dict[str, Any]:
        if hasattr(self._client, "fetch_balance"):
            try:
                res = self._client.fetch_balance()
                return await res if hasattr(res, "__await__") else res
            except Exception as e:
                raise ExchangeError(f"Gagal mengambil saldo bursa: {e}") from e
        return {"free_margin": Decimal("10000.0"), "total_wallet_balance": Decimal("10000.0")}

    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        if hasattr(self._client, "fetch_ticker_price"):
            res = self._client.fetch_ticker_price(symbol=symbol)
            price = await res if hasattr(res, "__await__") else res
            return {"last": price, "price": price}
        if hasattr(self._client, "fetch_ticker"):
            res = self._client.fetch_ticker(symbol=symbol)
            return await res if hasattr(res, "__await__") else res
        return {"last": Decimal("50000.0")}

    async def set_leverage(self, symbol: str, leverage: int) -> Any:
        if hasattr(self._client, "set_leverage"):
            res = self._client.set_leverage(symbol=symbol, leverage=leverage)
            return await res if hasattr(res, "__await__") else res

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Any:
        if hasattr(self._client, "set_margin_mode"):
            res = self._client.set_margin_mode(symbol=symbol, margin_mode=margin_mode)
            return await res if hasattr(res, "__await__") else res

    async def create_order(
        self,
        symbol: str,
        side: Any,
        order_type: Any,
        qty: Decimal,
        price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if hasattr(self._client, "create_entry_order"):
            res = self._client.create_entry_order(symbol=symbol, side=str(side), order_type=str(order_type), qty=qty, price=price, client_order_id=client_order_id)
            ret = await res if hasattr(res, "__await__") else res
            if isinstance(ret, dict):
                ret.setdefault("status", "FILLED" if str(order_type).upper() == "MARKET" else "NEW")
                ret.setdefault("order_id", ret.get("id", "MOCK_ORDER_1"))
                ret.setdefault("exchange_order_id", ret.get("id", "MOCK_ORDER_1"))
                return ret
        return {
            "order_id": "MOCK_ORDER_1",
            "exchange_order_id": "MOCK_ORDER_1",
            "status": "FILLED" if str(order_type).upper() == "MARKET" else "NEW",
            "price": float(price or 0),
        }

    async def create_stop_loss_order(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self._client, "create_stop_loss_order"):
            res = self._client.create_stop_loss_order(*args, **kwargs)
            ret = await res if hasattr(res, "__await__") else res
            if isinstance(ret, dict):
                ret.setdefault("id", "MOCK_SL_1")
                ret.setdefault("order_id", ret.get("id", "MOCK_SL_1"))
                return ret
        return {"id": "MOCK_SL_1", "order_id": "MOCK_SL_1", "status": "NEW"}

    async def create_take_profit_order(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self._client, "create_take_profit_order"):
            res = self._client.create_take_profit_order(*args, **kwargs)
            ret = await res if hasattr(res, "__await__") else res
            if isinstance(ret, dict):
                ret.setdefault("id", "MOCK_TP_1")
                ret.setdefault("order_id", ret.get("id", "MOCK_TP_1"))
                return ret
        return {"id": "MOCK_TP_1", "order_id": "MOCK_TP_1", "status": "NEW"}

    async def has_price_reached_target(self, symbol: str, target_price: Decimal, *args: Any, **kwargs: Any) -> bool:
        if hasattr(self._client, "has_price_reached_target"):
            fn = getattr(self._client, "has_price_reached_target")
            if isinstance(fn, (AsyncMock, MagicMock)):
                try:
                    res = fn(symbol=symbol, target_price=target_price, *args, **kwargs) if not isinstance(fn, AsyncMock) else await fn(symbol=symbol, target_price=target_price, *args, **kwargs)
                    ret = await res if hasattr(res, "__await__") else res
                    if isinstance(ret, (AsyncMock, MagicMock)):
                        return False
                    return bool(ret)
                except Exception:
                    return False
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)



class TradeService:
    def __init__(
        self,
        instrument_repo=None,
        watchlist_repo=None,
        trade_repo=None,
        trade_risk_repo=None,
        daily_risk_repo=None,
        order_repo=None,
        trade_event_repo=None,
        risk_profile_repo=None,
        bracket_repo=None,
        exchange_gateway=None,
        risk_calculator=None,
        event_publisher=None,
    ):
        self.instrument_repo = instrument_repo
        self.watchlist_repo = watchlist_repo
        self.trade_repo = trade_repo
        self.trade_risk_repo = trade_risk_repo
        self.daily_risk_repo = daily_risk_repo
        self.order_repo = order_repo
        self.trade_event_repo = trade_event_repo
        self.risk_profile_repo = risk_profile_repo or (RiskProfileRepository(self.trade_repo.session) if hasattr(self.trade_repo, "session") else None)
        self.bracket_repo = bracket_repo
        self.exchange_gateway = MockExchangeGatewayAdapter(exchange_gateway) if exchange_gateway is not None else None
        self.risk_calculator = risk_calculator
        self.event_publisher = event_publisher


        self._execute_uc = ExecuteSignalUseCase(
            instrument_repo=self.instrument_repo,
            watchlist_repo=self.watchlist_repo,
            trade_repo=self.trade_repo,
            trade_risk_repo=self.trade_risk_repo,
            daily_risk_repo=self.daily_risk_repo,
            order_repo=self.order_repo,
            trade_event_repo=self.trade_event_repo,
            risk_profile_repo=self.risk_profile_repo,
            bracket_repo=self.bracket_repo,
            exchange_gateway=self.exchange_gateway,
            risk_calculator=self.risk_calculator,
            event_publisher=self.event_publisher,
        )

    async def execute_signal(self, signal_dto: ParsedSignalDTO, account_id: int = 1, strategy_id: int = None, auto_tp_sl: bool = True):
        cmd = ExecuteSignalCommand(
            signal_dto=signal_dto,
            account_id=account_id,
            strategy_id=strategy_id,
            auto_tp_sl=auto_tp_sl,
        )
        return await self._execute_uc.execute(cmd)


# =============================================================================
# 1. BINANCE EXCHANGE API NEGATIVE CASES
# =============================================================================

@pytest.mark.asyncio
async def test_binance_insufficient_margin_error(async_session: AsyncSession, seeded_env: dict):
    """Test handling of Binance API error -2019 (Margin is insufficient)."""
    env = seeded_env
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("50000.0"))
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
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
        risk_calculator=RiskCalculatorDomainService(),
        exchange_gateway=mock_binance,
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
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("50000.0"))
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
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
        risk_calculator=RiskCalculatorDomainService(),
        exchange_gateway=mock_binance,
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
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_binance.fetch_ticker_price = AsyncMock(return_value=Decimal("50000.0"))
    mock_binance.has_price_reached_target = AsyncMock(return_value=False)
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
        risk_calculator=RiskCalculatorDomainService(),
        exchange_gateway=mock_binance,
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
    """Test TelegramConnector handling HTTP 429 Rate Limit with retry_after parameter."""
    client = TelegramConnector(bot_token="test_token")
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
    """Test TelegramConnector handling HTTP 403 Forbidden (Bot blocked by user)."""
    client = TelegramConnector(bot_token="test_token")
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
    """Test TelegramConnector handling HTTP 400 entity parse error."""
    client = TelegramConnector(bot_token="test_token")

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


@pytest.mark.asyncio
async def test_binance_fetch_balance_failure_raises_exchange_error(async_session: AsyncSession, seeded_env: dict):
    """Verify that failing to fetch wallet balance raises ExchangeError and stops execution safely."""
    env = seeded_env
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(side_effect=Exception("Connection timed out to Binance API"))

    trade_service = TradeService(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=TradeRiskRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_calculator=RiskCalculatorDomainService(),
        exchange_gateway=mock_binance,
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

    with pytest.raises(ExchangeError) as exc_info:
        await trade_service.execute_signal(
            signal_dto=signal,
            account_id=env["account"].id,
            strategy_id=env["strategy"].id,
        )

    assert "Gagal mengambil saldo bursa" in str(exc_info.value)
