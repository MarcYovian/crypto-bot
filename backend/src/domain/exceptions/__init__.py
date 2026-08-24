"""Central export of all domain-level exceptions."""

from src.domain.exceptions.base import DomainError
from src.domain.exceptions.exchange import (
    ExchangeError,
    ExchangeNetworkError,
    ExchangeAuthError,
    InsufficientMarginError,
    InsufficientBalanceError,
    OrderRejectError,
    RateLimitError,
)
from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramNetworkError,
    TelegramSendError,
    TelegramMessageParseError,
)
from src.domain.exceptions.signal import (
    SignalParseError,
    InvalidSignalDataError,
)
from src.domain.exceptions.risk import (
    RiskCalculationError,
    ZeroStopDistanceError,
    MaxRiskExceededError,
    InsufficientMarginRiskError,
)
from src.domain.exceptions.trade import (
    TradeExecutionError,
    TradeNotFoundError,
    InvalidTradeStateError,
    PairAlreadyActiveError,
    SymbolNotWhitelistedError,
    DailyRiskLimitReachedError,
)
from src.domain.exceptions.auth import (
    AuthError,
    InvalidCredentialsError,
    AccountDisabledError,
    InvalidRefreshTokenError,
    UserNotFoundError,
)
from src.domain.exceptions.provider import (
    ProviderNotFoundError,
    DuplicateProviderError,
    StrategyNotFoundError,
    InvalidStrategyConfigError,
)

__all__ = [
    "DomainError",
    "ExchangeError",
    "ExchangeNetworkError",
    "ExchangeAuthError",
    "InsufficientMarginError",
    "InsufficientBalanceError",
    "OrderRejectError",
    "RateLimitError",
    "TelegramError",
    "TelegramAuthError",
    "TelegramRateLimitError",
    "TelegramNetworkError",
    "TelegramSendError",
    "TelegramMessageParseError",
    "SignalParseError",
    "InvalidSignalDataError",
    "RiskCalculationError",
    "ZeroStopDistanceError",
    "MaxRiskExceededError",
    "InsufficientMarginRiskError",
    "TradeExecutionError",
    "TradeNotFoundError",
    "InvalidTradeStateError",
    "PairAlreadyActiveError",
    "SymbolNotWhitelistedError",
    "DailyRiskLimitReachedError",
    "AuthError",
    "InvalidCredentialsError",
    "AccountDisabledError",
    "InvalidRefreshTokenError",
    "UserNotFoundError",
    "ProviderNotFoundError",
    "DuplicateProviderError",
    "StrategyNotFoundError",
    "InvalidStrategyConfigError",
]
