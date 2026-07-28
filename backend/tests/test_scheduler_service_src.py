import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.scheduler_service import CronSchedulerService
from src.services.execution_engine import BinanceExecutionEngine


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock(spec=BinanceExecutionEngine)
    engine.exchange = MagicMock()
    engine.exchange.fetch_balance = AsyncMock(return_value={'USDT': {'total': 1500.0}})
    engine.exchange.cancel_all_orders = AsyncMock()
    return engine


@pytest.mark.asyncio
async def test_cron_scheduler_service_init(mock_execution_engine):
    service = CronSchedulerService(mock_execution_engine)
    assert service.execution_engine == mock_execution_engine
    assert str(service.scheduler.timezone) == "Asia/Jakarta"


@pytest.mark.asyncio
async def test_failsafe_sync_matches_ccxt_unified_symbol(mock_execution_engine):
    """Test Bug #5 fix: failsafe sync correctly matches CCXT unified symbol format (BTC/USDT:USDT) with trade.symbol (BTCUSDT)."""
    from unittest.mock import patch
    from src.database.models import Trade

    # CCXT unified position format returns 'BTC/USDT:USDT'
    mock_execution_engine.fetch_positions = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'contracts': 0.05, 'positionAmt': 0.05}
    ])

    service = CronSchedulerService(mock_execution_engine)
    waiting_trade = Trade(id=1, symbol="BTCUSDT", side="BUY", status="WAITING_ENTRY")

    with patch("src.repository.trade_repository.TradeRepository.get_active_trades", AsyncMock(return_value=[waiting_trade])), \
         patch("src.repository.trade_repository.TradeRepository.update_trade_status", AsyncMock()) as mock_update, \
         patch("src.repository.trade_repository.TradeRepository.log_event", AsyncMock()):

        await service._job_failsafe_sync_check()
        mock_update.assert_called_once_with(1, "OPEN")
