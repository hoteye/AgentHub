from __future__ import annotations

import tempfile
from pathlib import Path

from cli.agent_cli.init_apply_runtime import apply_init_proposal


def test_apply_init_proposal_writes_split_rules_and_keeps_gitignore_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        proposal = {
            "project_root": str(root),
            "artifacts": [
                {
                    "path": str(root / "AENGTHUB.md"),
                    "kind": "project_doc",
                    "change_mode": "create",
                    "content": "# Demo\n",
                },
                {
                    "path": str(root / "AENGTHUB.override.md"),
                    "kind": "local_doc",
                    "change_mode": "create",
                    "content": "# Local\n",
                },
                {
                    "path": str(root / ".agenthub" / "rules" / "managed.md"),
                    "kind": "rules_doc",
                    "change_mode": "split_rules",
                    "content": "# Rule\n",
                },
            ],
        }

        first = apply_init_proposal(proposal)
        second = apply_init_proposal(proposal)

        assert (root / "AENGTHUB.md").read_text(encoding="utf-8") == "# Demo\n"
        assert (root / ".agenthub" / "rules" / "managed.md").read_text(encoding="utf-8") == "# Rule\n"
        assert str(root / ".agenthub" / "rules" / "managed.md") in first["created_paths"]
        gitignore_lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert gitignore_lines.count("/AENGTHUB.override.md") == 1
        assert second["gitignore_updated"] is False
