"""Dashboard websocket: streams telemetry + agent actions + lifecycle events."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.pubsub_service import CHANNEL_AGENT, CHANNEL_LIFECYCLE, CHANNEL_TELEMETRY, get_redis_client

router = APIRouter()

_active_ws_ids: set[int] = set()


def get_active_websocket_connection_count() -> int:
    return len(_active_ws_ids)


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket) -> None:
    await websocket.accept()
    ws_id = id(websocket)
    _active_ws_ids.add(ws_id)

    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(CHANNEL_TELEMETRY, CHANNEL_AGENT, CHANNEL_LIFECYCLE)

    try:
        async for message in pubsub.listen():
            if message is None:
                continue
            if message.get("type") != "message":
                continue

            data = message.get("data")
            if data is None:
                continue

            # Data is already JSON string from Redis publisher.
            if isinstance(data, (bytes, bytearray)):
                data_text = data.decode("utf-8", errors="ignore")
            else:
                data_text = str(data)
            await websocket.send_text(data_text)
    except WebSocketDisconnect:
        return
    finally:
        _active_ws_ids.discard(ws_id)
        try:
            await pubsub.close()
        except Exception:
            pass
        try:
            await redis_client.close()
        except Exception:
            pass

