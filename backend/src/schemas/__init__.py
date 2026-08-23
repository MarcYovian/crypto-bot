"""Centralized exports for all Pydantic schemas and DTOs."""

from src.schemas.common import (
    BaseSchema,
    TimestampMixin,
    PaginatedResponse,
)

from src.schemas.master import (
    ExchangeBase,
    ExchangeCreate,
    ExchangeUpdate,
    ExchangeRead,
    TradingAccountBase,
    TradingAccountCreate,
    TradingAccountUpdate,
    TradingAccountRead,
    TradingCredentialBase,
    TradingCredentialCreate,
    TradingCredentialUpdate,
    TradingCredentialRead,
    InstrumentBase,
    InstrumentCreate,
    InstrumentUpdate,
    InstrumentRead,
    InstrumentLeverageBracketBase,
    InstrumentLeverageBracketCreate,
    InstrumentLeverageBracketUpdate,
    InstrumentLeverageBracketRead,
    StrategyBase,
    StrategyCreate,
    StrategyUpdate,
    StrategyRead,
    SignalProviderBase,
    SignalProviderCreate,
    SignalProviderUpdate,
    SignalProviderRead,
    RiskProfileBase,
    RiskProfileCreate,
    RiskProfileUpdate,
    RiskProfileRead,
    WatchlistBase,
    WatchlistCreate,
    WatchlistUpdate,
    WatchlistRead,
)

from src.schemas.signal import (
    ParsedSignalDTO,
    TradingSignalBase,
    TradingSignalCreate,
    TradingSignalUpdate,
    TradingSignalRead,
    SignalConfirmationDTO,
)

from src.schemas.risk import (
    DailyRiskConfigBase,
    DailyRiskConfigCreate,
    DailyRiskConfigRead,
    TradeRiskBase,
    TradeRiskCreate,
    TradeRiskRead,
    RiskCalculationResultDTO,
)

from src.schemas.trade import (
    TradeBase,
    TradeCreate,
    TradeUpdate,
    TradeStatusUpdate,
    TradeRead,
    TradeDetailRead,
)

from src.schemas.order import (
    OrderBase,
    OrderCreate,
    OrderStatusUpdate,
    OrderRead,
    ExecutionBase,
    ExecutionCreate,
    ExecutionRead,
)

from src.schemas.event_summary import (
    TradeEventBase,
    TradeEventCreate,
    TradeEventRead,
    TradeSummaryBase,
    TradeSummaryCreate,
    TradeSummaryRead,
    PerformanceSummaryDTO,
)

from src.schemas.system import (
    BotSettingBase,
    BotSettingCreate,
    BotSettingUpdate,
    BotSettingRead,
    BotLogBase,
    BotLogCreate,
    BotLogRead,
)

from src.schemas.user import (
    UserDTO,
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
    UserCreateRequest,
    UserUpdatePasswordRequest,
)

from src.schemas.analytics import (
    AnalyticsSummaryDTO,
    EquityPointDTO,
)

__all__ = [
    # Common
    "BaseSchema",
    "TimestampMixin",
    "PaginatedResponse",
    # Master
    "ExchangeBase",
    "ExchangeCreate",
    "ExchangeUpdate",
    "ExchangeRead",
    "TradingAccountBase",
    "TradingAccountCreate",
    "TradingAccountUpdate",
    "TradingAccountRead",
    "TradingCredentialBase",
    "TradingCredentialCreate",
    "TradingCredentialUpdate",
    "TradingCredentialRead",
    "InstrumentBase",
    "InstrumentCreate",
    "InstrumentUpdate",
    "InstrumentRead",
    "InstrumentLeverageBracketBase",
    "InstrumentLeverageBracketCreate",
    "InstrumentLeverageBracketUpdate",
    "InstrumentLeverageBracketRead",
    "StrategyBase",
    "StrategyCreate",
    "StrategyUpdate",
    "StrategyRead",
    "SignalProviderBase",
    "SignalProviderCreate",
    "SignalProviderUpdate",
    "SignalProviderRead",
    "RiskProfileBase",
    "RiskProfileCreate",
    "RiskProfileUpdate",
    "RiskProfileRead",
    "WatchlistBase",
    "WatchlistCreate",
    "WatchlistUpdate",
    "WatchlistRead",
    # Signal
    "ParsedSignalDTO",
    "TradingSignalBase",
    "TradingSignalCreate",
    "TradingSignalUpdate",
    "TradingSignalRead",
    "SignalConfirmationDTO",
    # Risk
    "DailyRiskConfigBase",
    "DailyRiskConfigCreate",
    "DailyRiskConfigRead",
    "TradeRiskBase",
    "TradeRiskCreate",
    "TradeRiskRead",
    "RiskCalculationResultDTO",
    # Trade
    "TradeBase",
    "TradeCreate",
    "TradeUpdate",
    "TradeStatusUpdate",
    "TradeRead",
    "TradeDetailRead",
    # Order & Execution
    "OrderBase",
    "OrderCreate",
    "OrderStatusUpdate",
    "OrderRead",
    "ExecutionBase",
    "ExecutionCreate",
    "ExecutionRead",
    # Event & Summary
    "TradeEventBase",
    "TradeEventCreate",
    "TradeEventRead",
    "TradeSummaryBase",
    "TradeSummaryCreate",
    "TradeSummaryRead",
    "PerformanceSummaryDTO",
    # System & Log
    "BotSettingBase",
    "BotSettingCreate",
    "BotSettingUpdate",
    "BotSettingRead",
    "BotLogBase",
    "BotLogCreate",
    "BotLogRead",
    # User & Auth
    "UserDTO",
    "LoginRequest",
    "LoginResponse",
    "TokenRefreshRequest",
    "UserCreateRequest",
    "UserUpdatePasswordRequest",
    # Analytics
    "AnalyticsSummaryDTO",
    "EquityPointDTO",
]


