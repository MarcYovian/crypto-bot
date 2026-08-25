"""FastAPI WebSocket controller for real-time dashboard streaming."""

import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from src.utils.security import decode_token
from src.api.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def _handle_websocket_lifecycle(websocket: WebSocket, token: Optional[str] = None) -> None:
    """Validate token, accept websocket handshake, and manage message loop."""
    # 1. Authenticate query parameter token
    if not token or not token.strip():
        logger.warning("Rejecting WebSocket connection: Missing token query parameter.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token.")
        return

    try:
        payload = decode_token(token.strip())
        username: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")

        if username is None or token_type != "access":
            logger.warning("Rejecting WebSocket connection: Invalid token payload or token type.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload.")
            return
    except Exception as e:
        logger.warning(f"Rejecting WebSocket connection: Token decode failed ({e}).")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token.")
        return

    # 2. Register connection
    await ws_manager.connect(websocket)
    await ws_manager.send_personal_message(
        websocket,
        "CONNECTED",
        {"message": "WebSocket streaming connected successfully", "user": username},
    )

    # 3. Keep-alive / message receive loop
    try:
        while True:
            text = await websocket.receive_text()
            if text.strip().lower() == "ping":
                await ws_manager.send_personal_message(websocket, "PONG", {"status": "alive"})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket closed unexpectedly: {e}")
        await ws_manager.disconnect(websocket)


@router.websocket("/api/v1/ws")
async def websocket_endpoint_v1(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None, description="JWT Access Token"),
) -> None:
    """Primary WebSocket real-time event streaming endpoint."""
    await _handle_websocket_lifecycle(websocket, token)


@router.websocket("/ws")
async def websocket_endpoint_root(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None, description="JWT Access Token"),
) -> None:
    """Alternative root WebSocket endpoint for convenience."""
    await _handle_websocket_lifecycle(websocket, token)
