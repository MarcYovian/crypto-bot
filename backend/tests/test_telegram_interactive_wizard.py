"""Unit and integration tests for TelegramBotService interactive wizard and commands."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, BotLog
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService
from src.services.trade_service import TradeService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient
from src.services.telegram_service import TelegramService

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
async def tg_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Binance TESTNET Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.flush()

    inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    watch = Watchlist(instrument_id=inst.id, enabled=True)
    async_session.add(watch)

    log = BotLog(level="ERROR", module="TradeService", message="Binance margin test error")
    async_session.add(log)

    await async_session.commit()
    await async_session.refresh(account)
    await async_session.refresh(inst)

    def create_service(mock_binance=None, mock_tg=None):
        return TelegramService(
            signal_parser=SignalParserService(),
            risk_calculator=RiskCalculatorService(),
            trade_service=MagicMock(spec=TradeService),
            signal_repo=SignalRepository(async_session),
            trade_repo=TradeRepository(async_session),
            order_repo=OrderRepository(async_session),
            daily_risk_repo=DailyRiskRepository(async_session),
            trade_summary_repo=TradeSummaryRepository(async_session),
            watchlist_repo=WatchlistRepository(async_session),
            instrument_repo=InstrumentRepository(async_session),
            risk_profile_repo=RiskProfileRepository(async_session),
            bot_log_repo=BotLogRepository(async_session),
            bot_setting_repo=BotSettingRepository(async_session),
            exchange_repo=ExchangeRepository(async_session),
            trading_account_repo=TradingAccountRepository(async_session),
            trading_credential_repo=TradingCredentialRepository(async_session),
            binance_client=mock_binance or BinanceRestClient(),
            telegram_client=mock_tg or AsyncMock(spec=TelegramNotifierClient),
        )

    return {"exchange": exchange, "account": account, "inst": inst, "create_service": create_service}


@pytest.mark.asyncio
async def test_telegram_setup_wizard_full_flow(async_session: AsyncSession, tg_env: dict):
    """Test 3-step interactive setup wizard successfully connecting Binance API key."""
    env = tg_env
    mock_tg = AsyncMock(spec=TelegramNotifierClient)
    mock_binance = BinanceRestClient()

    bot_service = env["create_service"](mock_binance=mock_binance, mock_tg=mock_tg)
    chat_id = 998877

    # 1. Trigger wizard with callback WIZ_ENV_TESTNET
    res1 = await bot_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    assert res1["status"] == "WIZARD_STARTED"
    assert bot_service._wizard_state[str(chat_id)]["step"] == "AWAITING_API_KEY"

    # 2. User sends API Key
    res2 = await bot_service.handle_user_message("mock_api_key_1234567890", chat_id=chat_id)
    assert "API Key Diterima" in str(res2)
    assert bot_service._wizard_state[str(chat_id)]["step"] == "AWAITING_SECRET_KEY"

    # 3. User sends Secret Key (with mocked Binance handshake)
    with patch("src.services.telegram_service.BinanceRestClient") as MockClientClass:
        mock_instance = AsyncMock()
        mock_instance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("5000.0"), "free_margin": Decimal("4500.0")})
        mock_instance.close = AsyncMock()
        MockClientClass.return_value = mock_instance

        res3 = await bot_service.handle_user_message("mock_secret_key_1234567890", chat_id=chat_id, message_id=12)
        assert "AKUN BINANCE BERHASIL DIHUBUNGKAN" in str(res3)
        assert "$5,000.00" in str(res3)
        assert str(chat_id) not in bot_service._wizard_state

    # Verify credential was saved in DB
    cred_repo = TradingCredentialRepository(async_session)
    active_cred = await cred_repo.get_active_credential(env["account"].id)
    assert active_cred is not None
    assert active_cred.encrypted_api_key == "mock_api_key_1234567890"


@pytest.mark.asyncio
async def test_telegram_setup_wizard_handshake_failed(async_session: AsyncSession, tg_env: dict):
    """Test setup wizard when Binance API credentials reject handshake."""
    env = tg_env
    bot_service = env["create_service"]()

    chat_id = 112233
    await bot_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    await bot_service.handle_user_message("bad_api_key_1234567890", chat_id=chat_id)

    with patch("src.services.telegram_service.BinanceRestClient") as MockClientClass:
        mock_instance = AsyncMock()
        mock_instance.fetch_balance = AsyncMock(side_effect=Exception("Invalid API Key -2015"))
        mock_instance.close = AsyncMock()
        MockClientClass.return_value = mock_instance

        res = await bot_service.handle_user_message("bad_secret_key_1234567890", chat_id=chat_id)
        assert "Verifikasi Binance Gagal" in str(res)
        assert str(chat_id) not in bot_service._wizard_state


@pytest.mark.asyncio
async def test_telegram_setup_wizard_cancellation(async_session: AsyncSession, tg_env: dict):
    """Test cancelling the setup wizard via command and callback button."""
    env = tg_env
    bot_service = env["create_service"]()

    chat_id = 445566
    await bot_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    assert str(chat_id) in bot_service._wizard_state

    # Cancel via text
    cancel_res = await bot_service.handle_user_message("/cancel", chat_id=chat_id)
    assert "dibatalkan" in str(cancel_res)
    assert str(chat_id) not in bot_service._wizard_state

    # Cancel via callback
    await bot_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    cb_res = await bot_service.handle_callback_query("WIZ_CANCEL", message_id=10, chat_id=chat_id)
    assert cb_res["status"] == "WIZARD_CANCELLED"
    assert str(chat_id) not in bot_service._wizard_state


@pytest.mark.asyncio
async def test_telegram_watchlist_management_commands(async_session: AsyncSession, tg_env: dict):
    """Test /watchlist list, enable, and disable sub-commands."""
    env = tg_env
    bot_service = env["create_service"]()

    # 1. List watchlist
    list_res = await bot_service.handle_command("/watchlist")
    assert "BTCUSDT" in str(list_res)

    # 2. Disable BTCUSDT
    dis_res = await bot_service.handle_command("/watchlist disable BTCUSDT")
    assert "DINONAKTIFKAN" in str(dis_res)

    # 3. Enable BTCUSDT
    en_res = await bot_service.handle_command("/watchlist enable BTCUSDT")
    assert "DIAKTIFKAN" in str(en_res)


@pytest.mark.asyncio
async def test_telegram_logs_and_ping_commands(async_session: AsyncSession, tg_env: dict):
    """Test /logs fetching database errors and /ping diagnostic health check."""
    env = tg_env
    bot_service = env["create_service"]()

    # 1. /logs
    logs_res = await bot_service.handle_command("/logs")
    assert "ERROR LOG SISTEM" in str(logs_res)
    assert "Binance margin test error" in str(logs_res)

    # 2. /ping
    ping_res = await bot_service.handle_command("/ping")
    assert "PONG!" in str(ping_res)
    assert "Database Connection: 🟢 OK" in str(ping_res)
