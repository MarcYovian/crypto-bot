"""Application Layer - Use Cases, DTOs, and Event Handlers."""

from src.application.dto import (
    ExecuteSignalCommand,
    CloseTradeCommand,
    UpdateStopLossCommand,
    SyncPositionsCommand,
    OrderFillPayload,
    TradeExecutionResultDTO,
    SimulateRiskCommand,
    CheckDailyRiskCommand,
    ParseSignalCommand,
    ApproveSignalCommand,
    RejectSignalCommand,
)
from src.application.use_cases.trades import (
    ExecuteSignalUseCase,
    HandleOrderFillUseCase,
    CloseTradeUseCase,
    UpdateStopLossUseCase,
    SyncPositionsUseCase,
)
from src.application.use_cases.risk import (
    SimulateRiskUseCase,
    CheckDailyRiskUseCase,
)
from src.application.use_cases.signals import (
    ParseSignalUseCase,
    ApproveSignalUseCase,
    RejectSignalUseCase,
)
from src.application.use_cases.telegram import (
    HandleTelegramCommandUseCase,
)
from src.application.event_handlers import (
    TradeNotificationEventHandler,
)

__all__ = [
    # DTOs
    "ExecuteSignalCommand",
    "CloseTradeCommand",
    "UpdateStopLossCommand",
    "SyncPositionsCommand",
    "OrderFillPayload",
    "TradeExecutionResultDTO",
    "SimulateRiskCommand",
    "CheckDailyRiskCommand",
    "ParseSignalCommand",
    "ApproveSignalCommand",
    "RejectSignalCommand",
    # Use Cases
    "ExecuteSignalUseCase",
    "HandleOrderFillUseCase",
    "CloseTradeUseCase",
    "UpdateStopLossUseCase",
    "SyncPositionsUseCase",
    "SimulateRiskUseCase",
    "CheckDailyRiskUseCase",
    "ParseSignalUseCase",
    "ApproveSignalUseCase",
    "RejectSignalUseCase",
    "HandleTelegramCommandUseCase",
    # Event Handlers
    "TradeNotificationEventHandler",
]
