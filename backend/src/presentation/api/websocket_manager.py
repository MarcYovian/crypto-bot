"""Backward-compatibility facade for WebSocket manager.

Delegates to src.presentation.websocket.ws_manager.
"""

from src.presentation.websocket.ws_manager import WebSocketConnectionManager, ws_manager

WebSocketManager = WebSocketConnectionManager

__all__ = ["WebSocketConnectionManager", "WebSocketManager", "ws_manager"]
