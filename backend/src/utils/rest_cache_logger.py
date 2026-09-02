"""REST API request & response raw payload cache logger for Binance Futures.

Stores raw REST API requests and responses in separate JSON files:
- Request:  /var/log/cryptobot/binance_rest/<TELEGRAM_CHAT_ID>/cache/<timestamp>_<symbol>_<method>_REQ.json
- Response: /var/log/cryptobot/binance_rest/<TELEGRAM_CHAT_ID>/cache/<timestamp>_<symbol>_<method>_RES.json
"""

import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional, Union, Dict

from config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_REST_BASE_PATH = getattr(settings, "BINANCE_REST_LOG_PATH", "/var/log/cryptobot/binance_rest/")


def _path_name_parser(data: str) -> str:
    """Sanitize path name to avoid invalid characters."""
    regex = re.compile(r"[^a-zA-Z0-9_\-]")
    return regex.sub("", data)


def _default_json_serializer(obj: Any) -> Any:
    """Safely serialize non-standard JSON types like Decimal, datetime, etc."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _sanitize_payload(obj: Any) -> Any:
    """Recursively mask sensitive keys like apiKey, secret, signature in payloads."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("secret", "apikey", "api_key", "signature")):
                sanitized[k] = "***MASKED***"
            else:
                sanitized[k] = _sanitize_payload(v)
        return sanitized
    elif isinstance(obj, list):
        return [_sanitize_payload(item) for item in obj]
    elif isinstance(obj, tuple):
        return [_sanitize_payload(item) for item in obj]
    return obj


def _sync_atomic_write_cache(target_dir: str, filename: str, payload_str: str) -> str:
    """Synchronous worker that performs atomic write via temp file rename."""
    try:
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        rand_id = str(random.randint(1000, 9999))
        temp_path = f"{target_path}.tmp_{os.getpid()}_{rand_id}"

        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(payload_str)

        os.rename(temp_path, target_path)
        try:
            os.chmod(target_path, 0o666)
        except Exception:
            pass
        return target_path
    except Exception as e:
        logger.debug(f"Failed atomic writing REST cache to {target_dir}/{filename}: {e}")
        return ""


def extract_symbol_from_args(args: Any, kwargs: Any) -> str:
    """Helper to extract clean trading symbol from args or kwargs."""
    symbol = ""
    if args:
        for arg in args:
            if isinstance(arg, str) and ("USDT" in arg or "/" in arg or ":" in arg):
                symbol = arg
                break
    if not symbol and kwargs:
        symbol = str(kwargs.get("symbol") or "")

    if symbol:
        clean = re.sub(r"[^a-zA-Z0-9]", "", symbol).upper()
        return clean or "GLOBAL"
    return "GLOBAL"


async def write_rest_request_cache(
    method_name: str,
    args: Any,
    kwargs: Any,
    timestamp_str: str,
    symbol: Optional[str] = None,
    chat_id: Optional[Union[int, str]] = None,
    base_path: Optional[str] = None,
) -> str:
    """Asynchronously record raw REST request payload to JSON file.

    Format:
        {base_path}/{chat_id}/cache/{timestamp}_{symbol}_{method}_REQ.json
    """
    try:
        root_path = str(base_path or getattr(settings, "BINANCE_REST_LOG_PATH", "/var/log/cryptobot/binance_rest/") or "/var/log/cryptobot/binance_rest/")
        resolved_chat_id = chat_id or getattr(settings, "TELEGRAM_CHAT_ID", "846740826") or "default"
        clean_chat_id = _path_name_parser(str(resolved_chat_id))

        target_dir = os.path.join(root_path, clean_chat_id, "cache")
        clean_sym = _path_name_parser(symbol or extract_symbol_from_args(args, kwargs))
        clean_method = _path_name_parser(method_name)

        filename = f"{timestamp_str}_{clean_sym}_{clean_method}_REQ.json"

        request_data = {
            "timestamp": datetime.now().isoformat(),
            "method": method_name,
            "symbol": clean_sym,
            "args": _sanitize_payload(args),
            "kwargs": _sanitize_payload(kwargs),
        }

        payload_str = json.dumps(request_data, default=_default_json_serializer, indent=2)
        return await asyncio.to_thread(_sync_atomic_write_cache, target_dir, filename, payload_str)
    except Exception as exc:
        logger.debug("Failed to write REST request cache: %s", exc)
        return ""


async def write_rest_response_cache(
    method_name: str,
    response_data: Any,
    timestamp_str: str,
    symbol: Optional[str] = None,
    chat_id: Optional[Union[int, str]] = None,
    base_path: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> str:
    """Asynchronously record raw REST response payload to JSON file.

    Format:
        {base_path}/{chat_id}/cache/{timestamp}_{symbol}_{method}_RES.json
    """
    try:
        root_path = str(base_path or getattr(settings, "BINANCE_REST_LOG_PATH", "/var/log/cryptobot/binance_rest/") or "/var/log/cryptobot/binance_rest/")
        resolved_chat_id = chat_id or getattr(settings, "TELEGRAM_CHAT_ID", "846740826") or "default"
        clean_chat_id = _path_name_parser(str(resolved_chat_id))

        target_dir = os.path.join(root_path, clean_chat_id, "cache")
        clean_sym = _path_name_parser(symbol or "GLOBAL")
        clean_method = _path_name_parser(method_name)

        filename = f"{timestamp_str}_{clean_sym}_{clean_method}_RES.json"

        response_payload = {
            "timestamp": datetime.now().isoformat(),
            "method": method_name,
            "symbol": clean_sym,
            "duration_ms": duration_ms,
            "response": _sanitize_payload(response_data),
            "error": error,
        }

        payload_str = json.dumps(response_payload, default=_default_json_serializer, indent=2)
        return await asyncio.to_thread(_sync_atomic_write_cache, target_dir, filename, payload_str)
    except Exception as exc:
        logger.debug("Failed to write REST response cache: %s", exc)
        return ""
