"""WebSocket connection manager and real-time event broadcaster for Dashboard."""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert Decimal, datetime, and set instances to JSON-serializable types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(i) for i in obj]
    return obj


class WebSocketConnectionManager:
    """Singleton broker managing active client WebSocket connections and broadcasting events."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a client WebSocket connection and register in active set."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total active: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a client WebSocket connection gracefully."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active: {len(self.active_connections)}")

    async def send_personal_message(
        self,
        websocket: WebSocket,
        event: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a JSON event payload directly to a specific connected client."""
        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": _sanitize_for_json(data or {}),
        }
        try:
            await websocket.send_json(payload)
        except Exception as e:
            logger.warning(f"Failed to send personal WS message: {e}")
            await self.disconnect(websocket)

    async def broadcast(
        self,
        event: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Broadcast a standardized JSON event envelope to all active connected clients.

        Args:
            event: Event identifier (e.g., TRADE_OPENED, TP_HIT, SL_HIT, TRADE_CLOSED, CIRCUIT_BREAKER_TRIGGERED).
            data: Arbitrary structured data payload associated with the event.
        """
        async with self._lock:
            connections = list(self.active_connections)

        if not connections:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": _sanitize_for_json(data or {}),
        }

        stale_connections: List[WebSocket] = []

        async def _send(ws: WebSocket) -> None:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug(f"Error sending to WS client ({e}), marking for disconnect.")
                stale_connections.append(ws)

        await asyncio.gather(*[_send(ws) for ws in connections], return_exceptions=True)

        if stale_connections:
            async with self._lock:
                for dead_ws in stale_connections:
                    self.active_connections.discard(dead_ws)
            logger.info(
                f"Cleaned up {len(stale_connections)} stale WebSocket connections. Remaining: {len(self.active_connections)}"
            )


# Global singleton instance
ws_manager = WebSocketConnectionManager()
