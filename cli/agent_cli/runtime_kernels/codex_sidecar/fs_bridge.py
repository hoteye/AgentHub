from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


class CodexSidecarFsBridge:
    def __init__(self, *, kernel: Any, workspace_root: str | Path) -> None:
        self.kernel = kernel
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def read_file(self, path: str | Path) -> dict[str, Any]:
        raw = self.read_file_raw(path)
        return {
            "path": raw["path"],
            "content": raw["content_bytes"].decode("utf-8", errors="replace"),
            "data_base64": raw["data_base64"],
            "encoding": "utf-8",
            "decode_errors": "replace",
        }

    def read_file_raw(self, path: str | Path) -> dict[str, Any]:
        resolved = self._resolve_workspace_path(path)
        result = self.kernel.fs_read_file(str(resolved))
        data_base64 = str(result.get("dataBase64") or "")
        content_bytes = base64.b64decode(data_base64.encode("ascii"))
        return {
            "path": str(resolved),
            "content_bytes": content_bytes,
            "data_base64": data_base64,
        }

    def read_directory(self, path: str | Path) -> dict[str, Any]:
        resolved = self._resolve_workspace_path(path)
        result = self.kernel.fs_read_directory(str(resolved))
        entries = [
            {
                "name": str(item.get("fileName") or ""),
                "path": str(resolved / str(item.get("fileName") or "")),
                "is_directory": bool(item.get("isDirectory")),
                "is_file": bool(item.get("isFile")),
            }
            for item in list(result.get("entries") or [])
            if isinstance(item, dict) and str(item.get("fileName") or "").strip()
        ]
        return {"path": str(resolved), "entries": entries}

    def get_metadata(self, path: str | Path) -> dict[str, Any]:
        resolved = self._resolve_workspace_path(path)
        result = self.kernel.fs_get_metadata(str(resolved))
        return {
            "path": str(resolved),
            "is_directory": bool(result.get("isDirectory")),
            "is_file": bool(result.get("isFile")),
            "is_symlink": bool(result.get("isSymlink")),
            "created_at_ms": int(result.get("createdAtMs") or 0),
            "modified_at_ms": int(result.get("modifiedAtMs") or 0),
        }

    def _resolve_workspace_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PermissionError(f"path is outside workspace root: {resolved}") from exc
        return resolved
