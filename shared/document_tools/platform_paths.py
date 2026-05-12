from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, os.PathLike[str]]


def is_windows_native() -> bool:
    return sys.platform.startswith("win") and "WSL_DISTRO_NAME" not in os.environ


def is_wsl() -> bool:
    return "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ


def normalize_windows_path(path: PathLike) -> Path:
    raw = str(path or "").strip()
    if not raw:
        return Path(raw)
    if raw.startswith("/mnt/") and len(raw) > 6 and raw[5].isalpha() and raw[6] == "/":
        drive = raw[5].upper()
        remainder = raw[7:].replace("/", "\\")
        return Path(f"{drive}:\\{remainder}")
    return Path(raw)


def to_wsl_path(path: PathLike) -> Path:
    native = normalize_windows_path(path)
    if not native:
        return native
    if str(native).startswith("/"):
        return native
    result = subprocess.run(["wslpath", str(native)], capture_output=True, text=True)
    output = result.stdout.strip()
    return Path(output) if output else native


def get_temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def get_temp_image_path(filename: str = "desktop_capture.png") -> Path:
    return get_temp_dir() / filename


def find_soffice_executable() -> Optional[str]:
    env_value = os.environ.get("SOFFICE_PATH")
    if env_value:
        candidate = normalize_windows_path(env_value)
        if candidate.exists():
            return str(candidate)

    names = ["soffice.exe", "soffice"] if is_windows_native() else ["soffice"]
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved

    if is_windows_native():
        for root_env in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(root_env)
            if not root:
                continue
            candidate = Path(root) / "LibreOffice" / "program" / "soffice.exe"
            if candidate.exists():
                return str(candidate)
    return None
