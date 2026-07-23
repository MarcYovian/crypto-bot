import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.telegram_service import TelegramService
from src.services.execution_engine import BinanceExecutionEngine, ExecutionResponse
from src.services.precision_filter import SymbolInfo
from src.database.models import Trade


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock(spec=BinanceExecutionEngine)
    engine.fetch_symbol_info = AsyncMock(return_value=SymbolInfo("BTCUSDT", 2, 3, 0.10, 0.001, 0.001, 5.0))
    engine.execute_trade_pipeline = AsyncMock(return_value=ExecutionResponse(
        success=True, trade_id=1, execution_type="LIMIT", entry_order_id="998123"
    ))
    engine.exchange = MagicMock()
    engine.exchange.create_order = AsyncMock(return_value={'id': 'CLOSE_123', 'price': 60000.0, 'average': 60000.0})
    return engine


def test_telegram_service_initialization(mock_execution_engine):
    service = TelegramService(
        execution_engine=mock_execution_engine,
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_chat_id=998877
    )
    assert service.allowed_chat_id == 998877
    assert service.execution_engine == mock_execution_engine


@pytest.mark.asyncio
async def test_cmd_status_handler(mock_execution_engine):
    service = TelegramService(
        execution_engine=mock_execution_engine,
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_chat_id=998877
    )

    update = MagicMock()
    update.effective_chat.id = 998877
    update.message.reply_text = AsyncMock()

    mock_active_trade = Trade(
        id=1, symbol="BTCUSDT", side="BUY", status="OPEN",
        entry_price=60000.0, sl_price=59000.0, position_size=0.02, leverage=20
    )

    with patch("src.repository.trade_repository.TradeRepository.get_active_trades", AsyncMock(return_value=[mock_active_trade])):
        await service._cmd_status(update, MagicMock())
        update.message.reply_text.assert_called_once()
        assert "BTCUSDT" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_summary_handler(mock_execution_engine):
    service = TelegramService(
        execution_engine=mock_execution_engine,
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_chat_id=998877
    )

    update = MagicMock()
    update.effective_chat.id = 998877
    update.message.reply_text = AsyncMock()

    mock_summary = {
        "total_trades": 10,
        "winning_trades": 7,
        "losing_trades": 3,
        "winrate": 70.0,
        "total_gross_pnl": 150.0,
        "total_net_pnl": 140.0,
        "total_commission": 10.0
    }

    with patch("src.repository.trade_repository.TradeRepository.get_performance_summary", AsyncMock(return_value=mock_summary)):
        await service._cmd_summary(update, MagicMock())
        update.message.reply_text.assert_called_once()
        assert "70.0%" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_close_handler(mock_execution_engine):
    service = TelegramService(
        execution_engine=mock_execution_engine,
        token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_chat_id=998877
    )

    update = MagicMock()
    update.effective_chat.id = 998877
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = ["BTCUSDT"]

    mock_active_trade = Trade(
        id=1, symbol="BTCUSDT", side="BUY", status="OPEN",
        entry_price=60000.0, sl_price=59000.0, position_size=0.02, remaining_qty=0.02, leverage=20
    )

    with patch("src.repository.trade_repository.TradeRepository.get_active_trades", AsyncMock(return_value=[mock_active_trade])), \
         patch("src.repository.trade_repository.TradeRepository.update_trade_status", AsyncMock()), \
         patch("src.repository.trade_repository.TradeRepository.log_event", AsyncMock()):

        await service._cmd_close(update, context)
        mock_execution_engine.exchange.create_order.assert_called_with(
            symbol="BTCUSDT", type="market", side="sell", amount=0.02, params={"reduceOnly": True}
        )
        update.message.reply_text.assert_called_once()
