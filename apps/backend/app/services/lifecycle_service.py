"""Lifecycle event publisher/persister."""

from __future__ import annotations

from typing import Any

from app.database.models import LifecycleEventLog, utcnow
from app.database.session import get_session_factory
from app.services.pubsub_service import CHANNEL_LIFECYCLE, RedisPubSub, get_redis_client


async def emit_lifecycle_event(
    *,
    shipment_id: int,
    event_name: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Persist event to Postgres and publish it to Redis for websocket consumers."""
    redis_client = get_redis_client()
    pubsub = RedisPubSub(redis_client)

    try:
        # Persist to DB.
        factory = get_session_factory()
        async with factory() as session:
            ts = utcnow()
            row = LifecycleEventLog(
                shipment_id=shipment_id,
                timestamp=ts,
                event=event_name,
                payload_json=payload,
            )
            session.add(row)
            await session.commit()

        msg = {
            "type": "lifecycle_event",
            "shipment_id": shipment_id,
            "timestamp": utcnow().isoformat(),
            "payload": {"event_name": event_name, **(payload or {})},
        }
        await pubsub.publish_json(CHANNEL_LIFECYCLE, msg)
    finally:
        try:
            await redis_client.close()
        except Exception:
            pass

