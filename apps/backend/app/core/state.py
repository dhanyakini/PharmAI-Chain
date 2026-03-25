"""Process-wide app state (only what is needed for `/health`)."""

from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class AppState:
    db_ready: bool = False
    redis_connected: bool = False


app_state = AppState()
