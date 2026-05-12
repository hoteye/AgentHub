from __future__ import annotations

import configparser
from pathlib import Path

import pytest

import conftest as pytest_root_conftest

ROOT = Path(__file__).resolve().parents[1]
PYTEST_INI = ROOT / "pytest.ini"


def _load_pytest_ini() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    return parser["pytest"]


@pytest.mark.parametrize(
    ("relpath", "expected_markers"),
    [
        ("cli/tests/test_browser_tool_live.py", {"live", "browser"}),
        ("cli/tests/test_provider_status.py", {"heavy"}),
        ("cli/tests/test_gateway_methods_browser.py", {"browser"}),
        ("tests/test_web_automation_live_driver.py", {"browser"}),
        ("cli/tests/test_psbc_policy_plugin.py", {"policy_plugin"}),
        ("cli/tests/test_benchmark_headless_models.py", set()),
    ],
)
def test_markers_for_test_path_classifies_known_files(
    relpath: str,
    expected_markers: set[str],
) -> None:
    assert set(pytest_root_conftest.markers_for_test_path(relpath)) == expected_markers


def test_default_pytest_addopts_excludes_release_slow_markers() -> None:
    section = _load_pytest_ini()

    assert section["addopts"] == f'-m "{pytest_root_conftest.DEFAULT_ADDOPTS_MARKER_EXPRESSION}"'


def test_default_testpaths_stay_limited_to_repo_roots() -> None:
    section = _load_pytest_ini()

    assert section["testpaths"] == "tests cli/tests"


def test_python_test_files_do_not_carry_unittest_main_tail() -> None:
    offenders: list[str] = []
    current_test_path = Path(__file__).resolve()

    for rel_root in ("tests", "cli/tests"):
        for path in sorted((ROOT / rel_root).rglob("test_*.py")):
            if path.resolve() == current_test_path:
                continue
            text = path.read_text(encoding="utf-8")
            if 'if __name__ == "__main__":' in text or "unittest.main(" in text:
                offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_cli_tests_do_not_use_per_file_sys_path_injection() -> None:
    offenders: list[str] = []
    blocked_patterns = (
        "sys.path.insert(0, str(ROOT))",
        "if str(ROOT) not in sys.path:",
    )

    for path in sorted((ROOT / "cli/tests").rglob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in blocked_patterns):
            offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
