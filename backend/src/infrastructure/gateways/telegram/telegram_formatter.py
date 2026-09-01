"""Formatter for Telegram HTML notifications, cards, and inline keyboard layouts."""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union


class TelegramFormatter:
    """Provides formatting utilities for Telegram HTML messages and interactive markups."""

    @staticmethod
    def format_crypto_price(val: Any, precision: Optional[int] = None) -> str:
        """Format crypto price dynamically based on magnitude and precision."""
        if val is None:
            return "N/A"
        try:
            d = Decimal(str(val))
        except Exception:
            return str(val)

        if precision is not None and precision > 0:
            prec = precision
        elif abs(d) >= Decimal("1000"):
            prec = 2
        elif abs(d) >= Decimal("1"):
            prec = 4
        elif abs(d) > Decimal("0"):
            prec = 8
        else:
            prec = 2

        if abs(d) >= Decimal("1000"):
            s = f"{d:,.{prec}f}"
        else:
            s = f"{d:.{prec}f}"

        if "." in s:
            parts = s.split(".")
            integer_part = parts[0]
            dec_part = parts[1].rstrip("0")
            if len(dec_part) == 0:
                return f"{integer_part}.00"
            elif len(dec_part) == 1:
                return f"{integer_part}.{dec_part}0"
            else:
                return f"{integer_part}.{dec_part}"
        return s

    @staticmethod
    def format_crypto_qty(val: Any, precision: Optional[int] = None) -> str:
        """Format crypto quantity cleanly without unnecessary trailing zeroes."""
        if val is None:
            return "0"
        try:
            d = Decimal(str(val))
        except Exception:
            return str(val)

        if precision is not None and precision > 0:
            s = f"{d:.{precision}f}".rstrip("0").rstrip(".") if "." in f"{d:.{precision}f}" else f"{d:.{precision}f}"
        else:
            s = f"{d:.8f}".rstrip("0").rstrip(".")
        return s or "0"


    @classmethod
    def format_alert_html(cls, title: str, message: str, level: str = "INFO") -> str:
        """Format an alert notification with level-appropriate iconography."""
        level_upper = level.upper()
        if level_upper in ("CRITICAL", "ERROR", "PANIC"):
            icon = "🚨"
            header = f"<b>{icon} CRITICAL ALERT: {title}</b>"
        elif level_upper in ("WARNING", "WARN"):
            icon = "⚠️"
            header = f"<b>{icon} WARNING: {title}</b>"
        elif level_upper in ("SUCCESS", "PROFIT"):
            icon = "✅"
            header = f"<b>{icon} SUCCESS: {title}</b>"
        else:
            icon = "ℹ️"
            header = f"<b>{icon} INFO: {title}</b>"

        return f"{header}\n\n{message}"

    @staticmethod
    def build_inline_keyboard(rows: List[List[Dict[str, str]]]) -> Dict[str, Any]:
        """Construct standard Telegram inline_keyboard reply_markup dictionary."""
        return {"inline_keyboard": rows}
