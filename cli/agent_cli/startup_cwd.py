from __future__ import annotations

import os
from pathlib import Path

STARTUP_CWD_ENV = "AGENTHUB_STARTUP_CWD"
STARTUP_CWD_LAUNCHER_ACTIVE_ENV = "AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE"
STARTUP_CWD_SOURCE_ENV = "AGENTHUB_STARTUP_CWD_SOURCE"
STARTUP_CWD_SOURCE_LAUNCHER = "launcher"


def capture_startup_cwd() -> Path:
    configured = str(os.environ.get(STARTUP_CWD_ENV) or "").strip()
    launcher_active = str(os.environ.get(STARTUP_CWD_LAUNCHER_ACTIVE_ENV) or "").strip()
    source = str(os.environ.get(STARTUP_CWD_SOURCE_ENV) or "").strip().lower()
    if configured and source == STARTUP_CWD_SOURCE_LAUNCHER and launcher_active == "1":
        return Path(configured).resolve()
    startup_cwd = Path.cwd().resolve()
    os.environ[STARTUP_CWD_ENV] = str(startup_cwd)
    return startup_cwd


def resolve_startup_cwd() -> Path:
    configured = str(os.environ.get(STARTUP_CWD_ENV) or "").strip()
    return Path(configured or Path.cwd()).resolve()
