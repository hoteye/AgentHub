import sys
from pathlib import Path

if not bool(getattr(sys, "frozen", False)):
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


def _main() -> int:
    from cli.agent_cli.startup_cwd import capture_startup_cwd

    capture_startup_cwd()
    from cli.agent_cli.main import main

    return int(main() or 0)


if __name__ == "__main__":
    raise SystemExit(_main())
