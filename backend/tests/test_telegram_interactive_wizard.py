"""Unit and integration tests for TelegramBotController and TelegramWizardManager."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, BotLog
from src.infrastructure.persistence.repositories.trading_credential_repository import TradingCredentialRepository
from src.presentation.telegram.bot_controller import TelegramBotController
from src.presentation.telegram.wizard_manager import TelegramWizardManager, wizard_states
from src.infrastructure.di.container import container



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

    def create_controller():
        return TelegramBotController(session=async_session)

    return {"exchange": exchange, "account": account, "inst": inst, "create_controller": create_controller}


@pytest.mark.asyncio
async def test_telegram_setup_wizard_full_flow(async_session: AsyncSession, tg_env: dict):
    """Test 3-step interactive setup wizard successfully connecting Binance API key."""
    env = tg_env
    controller = env["create_controller"]()
    chat_id = 998877

    # Mock notification gateway for auto-deletion verification
    mock_notif = AsyncMock()
    mock_notif.delete_message = AsyncMock(return_value={"ok": True})
    mock_notif.send_message = AsyncMock(return_value={"ok": True})
    controller.notification_gateway = mock_notif
    controller.wizard_manager.notification_gateway = mock_notif

    # 1. Trigger wizard with callback WIZ_ENV_TESTNET
    res1 = await controller.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    assert res1 == "WIZARD_STARTED"
    assert wizard_states[str(chat_id)]["step"] == "AWAITING_API_KEY"

    # 2. User sends API Key (message_id=11)
    res2 = await controller.handle_user_message("mock_api_key_1234567890", chat_id=chat_id, message_id=11)
    assert "API Key Diterima" in str(res2)
    assert wizard_states[str(chat_id)]["step"] in ("AWAITING_API_SECRET", "AWAITING_SECRET_KEY")
    mock_notif.delete_message.assert_any_call(chat_id=chat_id, message_id=11)

    # 3. User sends Secret Key (with mocked Binance handshake, message_id=12)
    mock_gateway = AsyncMock()
    mock_gateway.get_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("5000.0"), "free_margin": Decimal("4500.0")})
    mock_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("5000.0"), "free_margin": Decimal("4500.0")})
    mock_gateway.reconfigure = MagicMock()

    with patch.object(container, "exchange_gateway", mock_gateway):
        res3 = await controller.handle_user_message("mock_secret_key_1234567890", chat_id=chat_id, message_id=12)
        assert "AKUN BINANCE BERHASIL DIHUBUNGKAN" in str(res3)
        assert "$5,000.00" in str(res3)
        assert str(chat_id) not in wizard_states
        mock_notif.delete_message.assert_any_call(chat_id=chat_id, message_id=12)

    # Verify credential was saved in DB (encrypted at rest)
    from src.utils.security import decrypt_secret
    cred_repo = TradingCredentialRepository(async_session)
    active_cred = await cred_repo.get_active_credential(env["account"].id)
    assert active_cred is not None
    assert decrypt_secret(active_cred.encrypted_api_key) == "mock_api_key_1234567890"

    # 4. User runs /account command -> must display decrypted & masked API key (mock****7890) and balance
    controller.command_use_case.exchange_gateway = mock_gateway
    with patch.object(container, "exchange_gateway", mock_gateway):
        res_acc = await controller.handle_user_message("/account", chat_id=chat_id)
        assert "INFORMASI AKUN & KREDENSIAL AKTIF" in str(res_acc)
        assert "mock****7890" in str(res_acc)
        assert "$5,000.00 USDT" in str(res_acc)


@pytest.mark.asyncio
async def test_telegram_setup_wizard_handshake_failed(async_session: AsyncSession, tg_env: dict):
    """Test setup wizard when Binance API credentials reject handshake."""
    env = tg_env
    controller = env["create_controller"]()

    chat_id = 112233
    await controller.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    await controller.handle_user_message("bad_api_key_1234567890", chat_id=chat_id)

    mock_fail_gateway = AsyncMock()
    mock_fail_gateway.get_balance = AsyncMock(side_effect=Exception("Invalid API Key -2015"))
    mock_fail_gateway.fetch_balance = AsyncMock(side_effect=Exception("Invalid API Key -2015"))
    mock_fail_gateway.reconfigure = MagicMock()

    with patch.object(container, "exchange_gateway", mock_fail_gateway):
        res = await controller.handle_user_message("bad_secret_key_1234567890", chat_id=chat_id)
        assert "Verifikasi Binance Gagal" in str(res)
        assert str(chat_id) not in wizard_states




@pytest.mark.asyncio
async def test_telegram_setup_wizard_cancellation(async_session: AsyncSession, tg_env: dict):
    """Test cancelling the setup wizard via command and callback button."""
    env = tg_env
    controller = env["create_controller"]()

    chat_id = 445566
    await controller.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    assert str(chat_id) in wizard_states

    # Cancel via text
    cancel_res = await controller.handle_user_message("/cancel", chat_id=chat_id)
    assert "dibatalkan" in str(cancel_res)
    assert str(chat_id) not in wizard_states

    # Cancel via callback
    await controller.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)
    cb_res = await controller.handle_callback_query("WIZ_CANCEL", message_id=10, chat_id=chat_id)
    assert cb_res == "WIZARD_CANCELLED"
    assert str(chat_id) not in wizard_states


@pytest.mark.asyncio
async def test_telegram_watchlist_management_commands(async_session: AsyncSession, tg_env: dict):
    """Test /watchlist list, enable, and disable sub-commands."""
    env = tg_env
    controller = env["create_controller"]()

    # 1. List watchlist
    list_res = await controller.handle_user_message("/watchlist", chat_id=100)
    assert "BTCUSDT" in str(list_res)

    # 2. Disable BTCUSDT
    dis_res = await controller.handle_user_message("/watchlist disable BTCUSDT", chat_id=100)
    assert "DINONAKTIFKAN" in str(dis_res)

    # 3. Enable BTCUSDT
    en_res = await controller.handle_user_message("/watchlist enable BTCUSDT", chat_id=100)
    assert "DIAKTIFKAN" in str(en_res)


@pytest.mark.asyncio
async def test_telegram_logs_and_ping_commands(async_session: AsyncSession, tg_env: dict):
    """Test /logs fetching database errors and /ping diagnostic health check."""
    env = tg_env
    controller = env["create_controller"]()

    # 1. /logs
    logs_res = await controller.handle_user_message("/logs", chat_id=100)
    assert "ERROR LOG SISTEM" in str(logs_res)
    assert "Binance margin test error" in str(logs_res)

    # 2. /ping
    ping_res = await controller.handle_user_message("/ping", chat_id=100)
    assert "PONG!" in str(ping_res)
    assert "Database Connection: 🟢 OK" in str(ping_res)


@pytest.mark.asyncio
async def test_setup_account_command_does_not_double_send_in_polling(async_session: AsyncSession, tg_env: dict):
    """Problem 1 Test: Verify /setup_account sends inline keyboard once and returns None to prevent double send."""
    env = tg_env
    controller = env["create_controller"]()
    mock_notif = AsyncMock()
    mock_notif.send_message = AsyncMock(return_value={"ok": True})
    controller.notification_gateway = mock_notif

    res = await controller.handle_user_message("/setup_account", chat_id=888)
    # When notification_gateway is present, it directly sends the interactive card and returns None
    assert res is None
    mock_notif.send_message.assert_called_once()
    call_args = mock_notif.send_message.call_args[1]
    assert call_args["chat_id"] == 888
    assert "WIZARD SETUP AKUN" in call_args["text"]
    assert "inline_keyboard" in call_args["reply_markup"]


@pytest.mark.asyncio
async def test_setup_wizard_auto_deletes_both_api_and_secret_keys(async_session: AsyncSession, tg_env: dict):
    """Problem 2 Test: Verify both API key and Secret key messages are deleted from chat."""
    env = tg_env
    controller = env["create_controller"]()
    mock_notif = AsyncMock()
    mock_notif.delete_message = AsyncMock(return_value={"ok": True})
    controller.notification_gateway = mock_notif
    controller.wizard_manager.notification_gateway = mock_notif

    chat_id = 776655
    # Start wizard
    await controller.handle_callback_query("WIZ_ENV_TESTNET", message_id=10, chat_id=chat_id)

    # Send API Key (message_id=101)
    res_api = await controller.handle_user_message("my_secret_api_key_12345", chat_id=chat_id, message_id=101)
    assert "API Key Diterima" in str(res_api)
    mock_notif.delete_message.assert_any_call(chat_id=chat_id, message_id=101)

    # Send Secret Key (message_id=102)
    mock_gw = AsyncMock()
    mock_gw.get_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0"), "free_margin": Decimal("1000.0")})
    mock_gw.reconfigure = MagicMock()

    with patch.object(container, "exchange_gateway", mock_gw):
        res_sec = await controller.handle_user_message("my_secret_key_99999", chat_id=chat_id, message_id=102)
        assert "AKUN BINANCE BERHASIL DIHUBUNGKAN" in str(res_sec)
        mock_notif.delete_message.assert_any_call(chat_id=chat_id, message_id=102)


@pytest.mark.asyncio
async def test_account_command_displays_decrypted_masked_api_key_and_balance(async_session: AsyncSession, tg_env: dict):
    """Problem 3 Test: Verify /account decrypts ciphertext and displays masked real key instead of 'Belum Dikonfigurasi'."""
    env = tg_env
    controller = env["create_controller"]()

    # Create active credential in DB
    cred_repo = TradingCredentialRepository(async_session)
    await cred_repo.create({
        "account_id": env["account"].id,
        "key_name": "Testnet Key",
        "api_key": "binance_live_api_key_987654321",
        "secret_key": "binance_live_secret_key_123456789",
        "is_active": True,
    })

    mock_gw = AsyncMock()
    mock_gw.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("4355.05"), "free_margin": Decimal("4000.0")})
    controller.command_use_case.exchange_gateway = mock_gw

    res = await controller.handle_user_message("/account", chat_id=999)
    assert "INFORMASI AKUN & KREDENSIAL AKTIF" in str(res)
    # Masked real key from decrypted ciphertext: first 4 and last 4 chars
    assert "bina****4321" in str(res)
    assert "Belum Dikonfigurasi" not in str(res)
    assert "$4,355.05 USDT" in str(res)
