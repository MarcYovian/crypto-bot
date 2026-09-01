"""Telegram HTML and Markdown formatting utilities for Presentation layer."""

from decimal import Decimal
from typing import Any, Optional


def format_crypto_price(val: Any, precision: Optional[int] = None) -> str:
    """Format crypto price dynamically without losing decimals or adding redundant trailing zeroes."""
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
        return s if s else "0"
    s = f"{d:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"
