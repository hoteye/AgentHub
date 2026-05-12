from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from cli.scripts import import_boundary_guard


def test_import_boundary_main_passes_path_wrapped_root_to_changed_python_files(
    monkeypatch,
) -> None:
    expected_root = "cli/custom_scope"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        import_boundary_guard,
        "parse_args",
        lambda: Namespace(root=expected_root, base_ref="release/2026-04"),
    )

    def _changed_python_files(*, root: Path, base_ref: str):
        captured["root"] = root
        captured["base_ref"] = base_ref
        return []

    monkeypatch.setattr(import_boundary_guard, "changed_python_files", _changed_python_files)

    rc = import_boundary_guard.main()

    assert rc == 0
    assert captured["root"] == Path(expected_root)
    assert captured["base_ref"] == "release/2026-04"
