"""Unit tests for HandleTelegramCommandUseCase covering all 15 bot commands."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.telegram.handle_command_use_case import HandleTelegramCommandUseCase
from src.application.use_cases.trades.close_trade_use_case import CloseTradeUseCase
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway
from src.domain.ports.repositories import (
    IBotLogRepository,
    IBotSettingRepository,
    IDailyRiskRepository,
    IOrderRepository,
    ITradeRepository,
    ITradeSummaryRepository,
    ITradingAccountRepository,
    ITradingCredentialRepository,
    IWatchlistRepository,
)


@pytest.fixture
def mock_command_deps():
    trade_repo = MagicMock(spec=ITradeRepository)
    order_repo = MagicMock(spec=IOrderRepository)
    watchlist_repo = MagicMock(spec=IWatchlistRepository)
    bot_log_repo = MagicMock(spec=IBotLogRepository)
    daily_risk_repo = MagicMock(spec=IDailyRiskRepository)
    trade_summary_repo = MagicMock(spec=ITradeSummaryRepository)
    bot_setting_repo = MagicMock(spec=IBotSettingRepository)
    trading_account_repo = MagicMock(spec=ITradingAccountRepository)
    trading_credential_repo = MagicMock(spec=ITradingCredentialRepository)
    close_trade_uc = MagicMock(spec=CloseTradeUseCase)
    exchange_gateway = MagicMock(spec=IExchangeGateway)
    notification_gateway = MagicMock(spec=INotificationGateway)

    trade_repo.get_all_active_trades = AsyncMock(return_value=[])
    trade_repo.get = AsyncMock(return_value=None)
    watchlist_repo.get_all_active = AsyncMock(return_value=[])
    watchlist_repo.set_symbol_enabled = AsyncMock()
    bot_log_repo.get_recent_logs = AsyncMock(return_value=[])
    bot_log_repo.get_error_logs = AsyncMock(return_value=[])
    bot_setting_repo.set_value = AsyncMock()
    daily_risk_repo.get_by_date = AsyncMock(return_value=None)
    daily_risk_repo.get_latest_snapshot = AsyncMock(return_value=None)
    daily_risk_repo.get_or_create_daily_snapshot = AsyncMock(
        return_value=MagicMock(id=1, balance=Decimal("10000"), risk_amount=Decimal("200"))
    )
    daily_risk_repo.get_remaining_risk_budget = AsyncMock(return_value=Decimal("150"))
    daily_risk_repo.get_total_margin_used = AsyncMock(return_value=Decimal("500"))
    trade_summary_repo.get_performance_summary = AsyncMock(
        return_value={
            "total_trades": 10,
            "winning_trades": 7,
            "losing_trades": 3,
            "win_rate": 70.0,
            "total_net_pnl": Decimal("1500.0"),
            "total_commission": Decimal("12.5"),
        }
    )
    trading_account_repo.get = AsyncMock(return_value=MagicMock(is_testnet=True))
    trading_credential_repo.get_active_credential = AsyncMock(
        return_value=MagicMock(encrypted_api_key="APIKEY12345678")
    )
    exchange_gateway.fetch_balance = AsyncMock(
        return_value={
            "total_wallet_balance": Decimal("10000"),
            "free_margin": Decimal("8500"),
            "unrealized_pnl": Decimal("250"),
        }
    )
    notification_gateway.send_message = AsyncMock()
    close_trade_uc.execute = AsyncMock(return_value={"status": "CLOSED"})
    close_trade_uc.panic_close_all = AsyncMock(return_value=[{"status": "CLOSED"}])

    return {
        "trade_repo": trade_repo,
        "order_repo": order_repo,
        "watchlist_repo": watchlist_repo,
        "bot_log_repo": bot_log_repo,
        "daily_risk_repo": daily_risk_repo,
        "trade_summary_repo": trade_summary_repo,
        "bot_setting_repo": bot_setting_repo,
        "trading_account_repo": trading_account_repo,
        "trading_credential_repo": trading_credential_repo,
        "close_trade_use_case": close_trade_uc,
        "exchange_gateway": exchange_gateway,
        "notification_gateway": notification_gateway,
    }


@pytest.mark.asyncio
async def test_all_15_commands_execution(mock_command_deps):
    use_case = HandleTelegramCommandUseCase(**mock_command_deps)

    # 1. /help
    res_help = await use_case.execute_command("/help")
    assert "DAFTAR LENGKAP PERINTAH" in res_help

    # 2. /setup_account
    res_setup = await use_case.execute_command("/setup_account", chat_id="12345")
    assert "WIZARD SETUP AKUN" in res_setup
    mock_command_deps["notification_gateway"].send_message.assert_awaited_once()

    # 3. /account
    res_acc = await use_case.execute_command("/account")
    assert "INFORMASI AKUN" in res_acc
    assert "APIK****5678" in res_acc

    # 4. /balance
    res_bal = await use_case.execute_command("/balance")
    assert "RINGKASAN SALDO" in res_bal
    assert "10,000.00 USDT" in res_bal

    # 5. /status
    res_status = await use_case.execute_command("/status")
    assert "Tidak ada posisi aktif" in res_status

    # 6. /pending
    res_pending = await use_case.execute_command("/pending")
    assert "Tidak ada limit order" in res_pending

    # 7. /summary
    res_sum = await use_case.execute_command("/summary")
    assert "70.0%" in res_sum
    assert "1,500.00 USDT" in res_sum

    # 8. /circuit_breaker
    res_cb = await use_case.execute_command("/circuit_breaker")
    assert "STATUS CIRCUIT BREAKER" in res_cb
    assert "NORMAL" in res_cb

    # 9. /close
    res_close = await use_case.execute_command("/close 15")
    assert "Berhasil menutup" in res_close
    mock_command_deps["close_trade_use_case"].execute.assert_awaited_once()

    # 10. /panic
    res_panic = await use_case.execute_command("/panic")
    assert "EMERGENCY PANIC CLOSE" in res_panic
    mock_command_deps["close_trade_use_case"].panic_close_all.assert_awaited_once()

    # 11. /pause
    res_pause = await use_case.execute_command("/pause")
    assert "BOT PAUSED" in res_pause
    mock_command_deps["bot_setting_repo"].set_value.assert_awaited_with(
        "is_trading_paused", "true", setting_type="BOOLEAN", category="TRADING"
    )

    # 12. /resume
    res_resume = await use_case.execute_command("/resume")
    assert "BOT RESUMED" in res_resume
    mock_command_deps["bot_setting_repo"].set_value.assert_awaited_with(
        "is_trading_paused", "false", setting_type="BOOLEAN", category="TRADING"
    )

    # 13. /watchlist
    res_wl = await use_case.execute_command("/watchlist add BTCUSDT")
    assert "ditambahkan" in res_wl
    mock_command_deps["watchlist_repo"].set_symbol_enabled.assert_awaited_with("BTCUSDT", True)

    # 14. /logs
    res_logs = await use_case.execute_command("/logs")
    assert "Tidak ada error log baru" in res_logs

    # 15. /ping
    res_ping = await use_case.execute_command("/ping")
    assert "Pong!" in res_ping
