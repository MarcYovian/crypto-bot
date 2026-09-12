"""Clean Architecture Application Use Cases."""

from src.application.use_cases.trades import (
    ExecuteSignalUseCase,
    HandleOrderFillUseCase,
    CloseTradeUseCase,
    GetActiveTradesUseCase,
    GetTradeHistoryUseCase,
    GetTradeDetailUseCase,
)
from src.application.use_cases.signals import (
    ParseSignalUseCase,
    ApproveSignalUseCase,
    RejectSignalUseCase,
    GetSignalsFeedUseCase,
    ManualExecuteSignalUseCase,
)
from src.application.use_cases.risk import (
    SimulateRiskUseCase,
)
from src.application.use_cases.telegram import (
    HandleTelegramCommandUseCase,
)
from src.application.use_cases.bot import (
    GetBotStatusUseCase,
    PauseBotUseCase,
    ResumeBotUseCase,
    PanicCloseUseCase,
    GetSettingsUseCase,
    UpdateSettingsUseCase,
    SaveCredentialsUseCase,
    CheckSystemHeartbeatUseCase,
)
from src.application.use_cases.analytics import (
    GetDashboardSummaryUseCase,
    GetEquityCurveUseCase,
)
from src.application.use_cases.auth import (
    LoginUseCase,
    RefreshTokenUseCase,
)
from src.application.use_cases.instruments import (
    ListInstrumentsUseCase,
    SyncInstrumentsUseCase,
)
from src.application.use_cases.watchlist import (
    GetWatchlistUseCase,
    ToggleWatchlistUseCase,
)
from src.application.use_cases.providers import (
    ListProvidersUseCase,
    CreateProviderUseCase,
    GetProviderPerformanceUseCase,
)
from src.application.use_cases.strategies import (
    ListStrategiesUseCase,
    UpdateStrategyUseCase,
)
from src.application.use_cases.reports import (
    ExportTradesCsvUseCase,
    SendDailyPerformanceReportUseCase,
)
from src.application.use_cases.logs import (
    GetLogsUseCase,
    PurgeOldLogsUseCase,
)

__all__ = [
    # Trades
    "ExecuteSignalUseCase",
    "HandleOrderFillUseCase",
    "CloseTradeUseCase",
    "GetActiveTradesUseCase",
    "GetTradeHistoryUseCase",
    "GetTradeDetailUseCase",
    # Signals
    "ParseSignalUseCase",
    "ApproveSignalUseCase",
    "RejectSignalUseCase",
    "GetSignalsFeedUseCase",
    "ManualExecuteSignalUseCase",
    # Risk
    "SimulateRiskUseCase",
    # Telegram
    "HandleTelegramCommandUseCase",
    # Bot
    "GetBotStatusUseCase",
    "PauseBotUseCase",
    "ResumeBotUseCase",
    "PanicCloseUseCase",
    "GetSettingsUseCase",
    "UpdateSettingsUseCase",
    "SaveCredentialsUseCase",
    "CheckSystemHeartbeatUseCase",
    # Analytics
    "GetDashboardSummaryUseCase",
    "GetEquityCurveUseCase",
    # Auth
    "LoginUseCase",
    "RefreshTokenUseCase",
    # Instruments
    "ListInstrumentsUseCase",
    "SyncInstrumentsUseCase",
    # Watchlist
    "GetWatchlistUseCase",
    "ToggleWatchlistUseCase",
    # Providers
    "ListProvidersUseCase",
    "CreateProviderUseCase",
    "GetProviderPerformanceUseCase",
    # Strategies
    "ListStrategiesUseCase",
    "UpdateStrategyUseCase",
    # Reports
    "ExportTradesCsvUseCase",
    "SendDailyPerformanceReportUseCase",
    # Logs
    "GetLogsUseCase",
    "PurgeOldLogsUseCase",
]
