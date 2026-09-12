"""Gateway cache logger for exchange interactions (REST & WebSocket).

Stores raw REST requests, REST responses, and WebSocket event streams.
Supports bi-directional read/write operations and automatic daily archiving.
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from config.settings import settings
from src.utils.file_cache.base_cache import (
    BaseFileCacheLogger,
    clean_path_name,
)


def extract_symbol_from_args(args: Any, kwargs: Any) -> str:
    """Helper to extract clean trading symbol from args or kwargs."""
    symbol = ""
    if args:
        for arg in args:
            if isinstance(arg, str) and ("USDT" in arg or "/" in arg or ":" in arg):
                symbol = arg
                break
    if not symbol and kwargs and isinstance(kwargs, dict):
        symbol = str(kwargs.get("symbol") or "")

    if symbol:
        # Strip colon suffix like ':USDT' in CCXT linear futures if present
        target_sym = symbol.split(":")[0] if ":" in symbol else symbol
        clean = re.sub(r"[^a-zA-Z0-9]", "", target_sym).upper()
        return clean or "GLOBAL"
    return "GLOBAL"


class GatewayCacheLogger(BaseFileCacheLogger):
    """Handles raw payload caching for specific gateways (e.g. Binance, Telegram)."""

    def __init__(
        self,
        gateway_name: str = "binance",
        base_path: Optional[str] = None,
        rest_base_path: Optional[str] = None,
        ws_base_path: Optional[str] = None,
        chat_id: Optional[Union[int, str]] = None,
    ) -> None:
        super().__init__(base_path=base_path, chat_id=chat_id)
        self.gateway_name = clean_path_name(gateway_name) or "binance"

        # Determine REST cache directory
        if rest_base_path:
            self.rest_base_path = rest_base_path
        elif base_path:
            self.rest_base_path = base_path
        elif self.gateway_name == "binance":
            self.rest_base_path = getattr(
                settings, "BINANCE_REST_LOG_PATH", "/var/log/cryptobot/binance_rest/"
            ) or "/var/log/cryptobot/binance_rest/"
        else:
            self.rest_base_path = f"/var/log/cryptobot/gateways/{self.gateway_name}/rest/"

        # Determine WebSocket cache directory
        if ws_base_path:
            self.ws_base_path = ws_base_path
        elif base_path:
            self.ws_base_path = base_path
        elif self.gateway_name == "binance":
            self.ws_base_path = getattr(
                settings, "WS_CACHE_LOG_PATH", "/var/log/cryptobot/wsbinance/"
            ) or "/var/log/cryptobot/wsbinance/"
        else:
            self.ws_base_path = f"/var/log/cryptobot/gateways/{self.gateway_name}/ws/"

    @property
    def rest_cache_dir(self) -> str:
        return os.path.join(self.rest_base_path, self.chat_id, "cache")

    @property
    def ws_cache_dir(self) -> str:
        return os.path.join(self.ws_base_path, self.chat_id, "cache")

    async def write_request_cache(
        self,
        method_name: str,
        args: Any,
        kwargs: Any,
        timestamp_str: str,
        symbol: Optional[str] = None,
    ) -> str:
        """Asynchronously record raw REST request payload to JSON file."""
        try:
            clean_sym = clean_path_name(symbol or extract_symbol_from_args(args, kwargs)) or "GLOBAL"
            clean_method = clean_path_name(method_name)
            filename = f"{timestamp_str}_{clean_sym}_{clean_method}_REQ.json"

            request_data = {
                "timestamp": datetime.now().isoformat(),
                "method": method_name,
                "symbol": clean_sym,
                "args": args,
                "kwargs": kwargs,
            }

            return await self.write_file_atomic(
                directory=self.rest_cache_dir,
                filename=filename,
                data=request_data,
                sanitize=True,
            )
        except Exception as e:
            return ""

    async def read_request_cache(
        self,
        timestamp_str: str,
        symbol: str,
        method_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Asynchronously read previously written REST request cache."""
        clean_sym = clean_path_name(symbol)
        clean_method = clean_path_name(method_name)
        filename = f"{timestamp_str}_{clean_sym}_{clean_method}_REQ.json"
        target_path = os.path.join(self.rest_cache_dir, filename)
        return await self.read_file_json(target_path)

    async def write_response_cache(
        self,
        method_name: str,
        response_data: Any,
        timestamp_str: str,
        symbol: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> str:
        """Asynchronously record raw REST response payload to JSON file."""
        try:
            clean_sym = clean_path_name(symbol or "GLOBAL") or "GLOBAL"
            clean_method = clean_path_name(method_name)
            filename = f"{timestamp_str}_{clean_sym}_{clean_method}_RES.json"

            response_payload = {
                "timestamp": datetime.now().isoformat(),
                "method": method_name,
                "symbol": clean_sym,
                "duration_ms": duration_ms,
                "response": response_data,
                "error": error,
            }

            return await self.write_file_atomic(
                directory=self.rest_cache_dir,
                filename=filename,
                data=response_payload,
                sanitize=True,
            )
        except Exception as e:
            return ""

    async def read_response_cache(
        self,
        timestamp_str: str,
        symbol: str,
        method_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Asynchronously read previously written REST response cache."""
        clean_sym = clean_path_name(symbol)
        clean_method = clean_path_name(method_name)
        filename = f"{timestamp_str}_{clean_sym}_{clean_method}_RES.json"
        target_path = os.path.join(self.rest_cache_dir, filename)
        return await self.read_file_json(target_path)

    async def write_ws_event_cache(
        self,
        order_data: Any,
        tag: str = "WSLISTENER",
        order_id: Optional[str] = None,
    ) -> str:
        """Asynchronously record raw Binance WebSocket order payload to JSON file."""
        if not order_data:
            return ""

        try:
            now = datetime.now()
            timestamp_str = now.strftime("%Y%m%d%H%M%S%f")

            parsed_order_id = ""
            if order_id:
                parsed_order_id = f"_{clean_path_name(str(order_id))}"
            elif isinstance(order_data, dict):
                raw_id = order_data.get("id") or order_data.get("orderId") or ""
                if raw_id:
                    parsed_order_id = f"_{clean_path_name(str(raw_id))}"

            clean_tag = clean_path_name(tag) or "WSLISTENER"
            filename = f"{timestamp_str}{parsed_order_id}_{clean_tag}.json"

            cache_entry = {
                "logged_at": now.isoformat(),
                "chat_id": self.chat_id,
                "tag": clean_tag,
                "data": order_data,
            }

            return await self.write_file_atomic(
                directory=self.ws_cache_dir,
                filename=filename,
                data=cache_entry,
                sanitize=True,
            )
        except Exception:
            return ""

    async def read_ws_event_cache(self, file_path_or_name: str) -> Optional[Dict[str, Any]]:
        """Read a WebSocket event cache by path or filename."""
        if os.path.isabs(file_path_or_name):
            target = file_path_or_name
        else:
            target = os.path.join(self.ws_cache_dir, file_path_or_name)
        return await self.read_file_json(target)

    async def archive(
        self,
        scope: str = "all",
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Archive cache directories into compressed .tar.gz files.

        Args:
            scope: 'all', 'ws', or 'rest'.
            now: Reference timestamp for naming.
        """
        curr_time = now or datetime.now()
        year_str = curr_time.strftime("%Y")
        month_str = curr_time.strftime("%m")
        day_str = curr_time.strftime("%d")
        date_time_str = curr_time.strftime("%Y-%m-%d_%H-%M-%S")

        results: List[Dict[str, Any]] = []

        targets = []
        ws_prefix = "wsbinance" if self.gateway_name == "binance" else f"ws_{self.gateway_name}"
        rest_prefix = "binance_rest" if self.gateway_name == "binance" else f"rest_{self.gateway_name}"
        if scope in ("all", "ws"):
            targets.append(("ws", self.ws_base_path, f"{ws_prefix}_{date_time_str}.tar.gz"))
        if scope in ("all", "rest"):
            targets.append(("rest", self.rest_base_path, f"{rest_prefix}_{date_time_str}.tar.gz"))

        for label, base_path, archive_filename in targets:
            if not os.path.exists(base_path):
                continue

            try:
                chat_dirs = [
                    d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))
                ]
            except Exception:
                continue

            for chat_id in chat_dirs:
                source_cache = os.path.join(base_path, chat_id, "cache")
                if not os.path.exists(source_cache) or not os.path.isdir(source_cache):
                    continue

                dest_dir = os.path.join(base_path, chat_id, "backup_cache", year_str, month_str, day_str)
                dest_archive_path = os.path.join(dest_dir, archive_filename)

                summary = await self.archive_directory(source_cache, dest_archive_path)
                if summary.get("archived_count", 0) > 0:
                    summary["chat_id"] = chat_id
                    summary["type"] = label
                    results.append(summary)

        return results
