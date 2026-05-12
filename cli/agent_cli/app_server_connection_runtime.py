from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _ConnectionState:
    initialized: bool = False
    initialized_notification_received: bool = False
    client_info: dict[str, Any] = field(default_factory=dict)
    connection_id: str = field(default_factory=lambda: f"conn_{uuid.uuid4().hex}")
