"""Centralised error categorisation and user-friendly Telegram error formatting."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FormattedError:
    """A structured, user-friendly error message for Telegram display.

    Attributes:
        title: Short error title.
        category: Error category (``RISK``, ``BALANCE``, ``EXCHANGE``, ``SYSTEM``).
        message: Human-readable explanation.
        action_advice: Suggested action for the user.
        code: Optional machine-readable error code.
        detail: Optional additional detail.
    """
    title: str
    category: str
    message: str
    action_advice: str
    code: Optional[str] = None
    detail: Optional[str] = None

    def to_telegram_markdown(self, symbol: str = "", side: str = "") -> str:
        """Render the error as a Telegram Markdown message with icons and formatting."""
        header_icon = {
            "RISK": "⚠️",
            "BALANCE": "🔴",
            "EXCHANGE": "⛔️",
            "SYSTEM": "🚨"
        }.get(self.category, "❌")

        pair_info = f"\nPair: `{symbol}` ({side})" if symbol else ""

        msg = (
            f"{header_icon} *{self.title.upper()}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━{pair_info}\n"
            f"*Cause*: {self.message}\n"
        )

        if self.detail:
            msg += f"*Detail*: {self.detail}\n"

        msg += f"\n*Suggested Action*:\n• {self.action_advice}\n"

        if self.code:
            msg += f"\n*Error Code*: `{self.code}`"

        return msg


class ErrorParser:
    """Categorise exceptions and convert them into structured ``FormattedError`` messages.

    Handles common Binance API error codes and internal risk-validation failures.
    """

    @staticmethod
    def parse_error(raw_error: Exception | str) -> FormattedError:
        """Parse an exception or error string into a structured ``FormattedError``.

        Matches against known Binance API error codes and internal validation
        messages.  Unrecognised errors fall through to a generic ``SYSTEM``
        category.

        Args:
            raw_error: The exception or error string to parse.

        Returns:
            A ``FormattedError`` with a category, user-facing message, and
            suggested action.
        """
        error_str = str(raw_error)

        if "-2019" in error_str or "Margin is insufficient" in error_str or "insufficient" in error_str.lower():
            return FormattedError(
                title="EXECUTION FAILED — INSUFFICIENT BALANCE",
                category="BALANCE",
                message="Your free margin balance is not enough to open this position.",
                action_advice="Reduce the daily risk percentage in bot settings, or deposit more USDT to your Futures account.",
                code="Binance API [-2019] Insufficient Margin"
            )

        elif "-4005" in error_str or "Quantity greater than max quantity" in error_str:
            return FormattedError(
                title="EXECUTION FAILED — EXCHANGE LIMIT",
                category="EXCHANGE",
                message="Order quantity exceeds the maximum market order limit allowed by Binance for this coin.",
                action_advice="Choose a coin with higher liquidity or use limit order execution.",
                code="Binance API [-4005] Max Quantity Exceeded"
            )

        elif "-1111" in error_str or "Precision is over" in error_str:
            return FormattedError(
                title="EXECUTION FAILED — PRICE/LOT PRECISION",
                category="EXCHANGE",
                message="Price or quantity decimal places do not conform to Binance exchange info rules.",
                action_advice="Ensure exchange precision filter data is up to date.",
                code="Binance API [-1111] Precision Overflow"
            )

        elif "cannot be identical" in error_str.lower():
            return FormattedError(
                title="SIGNAL REJECTED — RISK MANAGEMENT",
                category="RISK",
                message="Entry and Stop Loss prices are identical or too close together.",
                action_advice="Double-check the Entry & Stop Loss values in the Telegram signal.",
                code="Risk Calculator [INVALID_SL_DISTANCE]"
            )

        elif "min_notional" in error_str.lower() or "notional" in error_str.lower():
            return FormattedError(
                title="SIGNAL REJECTED — MINIMUM NOTIONAL",
                category="RISK",
                message="Total transaction value (Position Size × Entry) is below the Binance minimum ($5.0 USDT).",
                action_advice="Increase the daily risk percentage or choose a signal with adequate margin.",
                code="Binance Filter [MIN_NOTIONAL]"
            )

        else:
            clean_msg = error_str.replace("binanceusdm ", "").strip()
            if len(clean_msg) > 150:
                clean_msg = clean_msg[:150] + "..."

            return FormattedError(
                title="EXECUTION FAILED — SYSTEM ERROR",
                category="SYSTEM",
                message=clean_msg or "An internal error occurred while connecting to the exchange.",
                action_advice="Check the bot server logs for the full traceback.",
                code="SYSTEM_UNHANDLED_EXCEPTION"
            )

    # Static alias
    parse = parse_error
