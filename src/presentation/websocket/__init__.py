"""WebSocket Presentation Layer managing real-time broadcast and connection broker."""

from src.presentation.websocket.ws_manager import WebSocketConnectionManager, ws_manager

WebSocketManager = WebSocketConnectionManager

__all__ = ["WebSocketConnectionManager", "WebSocketManager", "ws_manager"]
