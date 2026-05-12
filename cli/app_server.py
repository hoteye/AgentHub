from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_paths() -> None:
    cli_root = Path(__file__).resolve().parent
    repo_root = cli_root.parent
    for candidate in (str(cli_root), str(repo_root)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


_ensure_import_paths()

from cli.agent_cli.app_server import main


if __name__ == "__main__":
    raise SystemExit(main())
