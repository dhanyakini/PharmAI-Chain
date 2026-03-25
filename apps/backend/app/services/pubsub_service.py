"""Redis pub/sub for telemetry and agent_actions channels."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

CHANNEL_TELEMETRY = "telemetry_stream"
CHANNEL_AGENT = "agent_actions"
CHANNEL_STATUS = "system_status"
CHANNEL_LIFECYCLE = "simulation_lifecycle"


class RedisPubSub:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def publish_json(self, channel: str, message: dict[str, Any]) -> None:
        await self._client.publish(channel, json.dumps(message, default=str))


def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)
