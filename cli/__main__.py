from pathlib import Path
import sys


_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cli.agent_cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
