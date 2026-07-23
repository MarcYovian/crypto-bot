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
