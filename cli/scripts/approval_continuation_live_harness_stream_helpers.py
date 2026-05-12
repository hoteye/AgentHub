from __future__ import annotations

import json
import select
import time
from pathlib import Path
from typing import Any


def _wait_for_json_line(stream: Any, *, timeout_seconds: int, tee_path: Path) -> dict[str, Any]:
    if stream is None:
        raise RuntimeError("serve stdout pipe is unavailable")
    deadline = time.time() + max(int(timeout_seconds), 1)
    buffer = ""
    while time.time() < deadline:
        remaining = max(deadline - time.time(), 0.1)
        ready, _, _ = select.select([stream], [], [], min(remaining, 1.0))
        if not ready:
            continue
        chunk = stream.readline()
        if not chunk:
            raise RuntimeError("serve stdout closed before response")
        tee_path.parent.mkdir(parents=True, exist_ok=True)
        with tee_path.open("a", encoding="utf-8") as handle:
            handle.write(chunk)
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            stripped = line.strip()
            if not stripped:
                continue
            return json.loads(stripped)
    raise TimeoutError(f"timed out waiting for serve response after {timeout_seconds}s")
