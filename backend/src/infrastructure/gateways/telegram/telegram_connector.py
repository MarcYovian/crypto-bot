"""Low-level HTTP connector for Telegram Bot API."""

import asyncio
import logging
from typing import Any, Dict, Optional, Union
import httpx

from src.domain.exceptions.telegram import (
    TelegramError,
    TelegramAuthError,
    TelegramRateLimitError,
    TelegramNetworkError,
    TelegramSendError,
    TelegramMessageParseError,
)

logger = logging.getLogger(__name__)


class TelegramConnector:
    """Manages raw HTTP requests to the Telegram Bot API."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        default_chat_id: Optional[Union[int, str]] = None,
        timeout: float = 15.0,
    ) -> None:
        self.bot_token = bot_token
        self.default_chat_id = str(default_chat_id) if default_chat_id else None
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        if not self.bot_token:
            return ""
        return f"https://api.telegram.org/bot{self.bot_token}"

    async def get_client(self) -> httpx.AsyncClient:
        """Get or initialize the persistent httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), trust_env=False)
        return self._client

    def _handle_response_error(self, resp: Any, operation: str = "execute_api") -> None:
        """Translate Telegram Bot API HTTP responses into Domain exceptions."""
        status_code = getattr(resp, "status_code", 500)
        try:
            error_data = resp.json() if callable(getattr(resp, "json", None)) else {}
        except Exception:
            error_data = {}

        desc = error_data.get("description", getattr(resp, "text", str(resp)))
        error_code = error_data.get("error_code", status_code)
        details = {"operation": operation, "status_code": status_code, "body": error_data}

        if error_code == 401:
            raise TelegramAuthError(f"Telegram Bot Token is invalid (401): {desc}", details=details)
        if error_code == 429:
            retry_after = error_data.get("parameters", {}).get("retry_after", 5)
            raise TelegramRateLimitError(
                f"Telegram Rate Limit (429): retry after {retry_after}s. {desc}",
                retry_after=int(retry_after),
                details=details,
            )
        if error_code == 400:
            if "can't parse entities" in desc.lower() or "entity parse" in desc.lower():
                raise TelegramMessageParseError(f"Telegram entity Parse error: {desc}", details=details)
            raise TelegramSendError(f"Telegram rejected message (400): {desc}", details=details)

        if error_code in (403, 404):
            raise TelegramSendError(f"Telegram rejected message ({error_code}): {desc}", details=details)

        raise TelegramError(f"Telegram API Error ({error_code}): {desc}", details=details)

    async def execute_api(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a POST request to Telegram Bot API with automatic error translation."""
        if not self.bot_token:
            logger.debug("Telegram Bot Token is not configured. Mocking execution for %s.", endpoint)
            return {"ok": True, "result": {"message_id": 999, "mock": True}}

        url = f"{self.base_url}/{endpoint}"
        client = await self.get_client()

        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()

            self._handle_response_error(resp, operation=endpoint)
            return resp.json()


        except httpx.TimeoutException as exc:
            logger.warning("Telegram request timed out for %s: %s", endpoint, exc)
            raise TelegramNetworkError(f"Telegram request timeout: {exc}") from exc
        except httpx.RequestError as exc:
            logger.warning("Telegram network connection error for %s: %s", endpoint, exc)
            raise TelegramNetworkError(f"Telegram network error: {exc}") from exc

    async def close(self) -> None:
        """Close the HTTP client session."""
        async with self._lock:
            if self._client and not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception as exc:
                    logger.warning("Error closing Telegram HTTP client: %s", exc)
                self._client = None

    async def start_polling(
        self,
        on_message_coro: Any = None,
        on_callback_query_coro: Any = None,
        poll_interval: float = 1.0,
    ) -> None:
        """Continuously poll Telegram getUpdates endpoint."""
        offset = 0
        while True:
            try:
                data = await self.execute_api("getUpdates", {"offset": offset, "timeout": 10})
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update.get("update_id", offset) + 1
                        if "message" in update and on_message_coro:
                            await on_message_coro(update["message"])
                        elif "callback_query" in update and on_callback_query_coro:
                            await on_callback_query_coro(update["callback_query"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Telegram polling error: %s", e)
                await asyncio.sleep(poll_interval)
