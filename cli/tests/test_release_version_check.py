from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "check_release_version.py"
SPEC = importlib.util.spec_from_file_location("check_release_version", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class ReleaseVersionCheckTest(unittest.TestCase):
    def test_extract_changelog_section_returns_matching_body(self) -> None:
        text = """# Changelog

## [Unreleased]

- next

## [0.1.0] - 2026-04-03

### Added

- first

## [0.0.9] - 2026-04-01

- older
"""
        section = MODULE.extract_changelog_section(text, "0.1.0")
        self.assertEqual(section, "### Added\n\n- first\n")

    def test_validate_release_ref_accepts_matching_tag(self) -> None:
        MODULE.validate_release_ref("0.1.0", "refs/tags/cli-v0.1.0")

    def test_validate_release_ref_rejects_mismatched_tag(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.validate_release_ref("0.1.0", "cli-v0.1.1")

    def test_main_writes_release_notes_for_matching_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "cli" / "agent_cli").mkdir(parents=True)
            (root / "cli" / "agent_cli" / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                """# Changelog

## [1.2.3] - 2026-04-03

- shipped
""",
                encoding="utf-8",
            )
            output = root / "release-notes.md"

            result = MODULE.main(
                [
                    "--repo-root",
                    str(root),
                    "--ref-name",
                    "cli-v1.2.3",
                    "--release-notes-out",
                    str(output),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "- shipped\n")
