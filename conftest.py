from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ADDOPTS_MARKER_EXPRESSION = "not live and not heavy and not policy_plugin"

LIVE_TEST_FILES = {
    "cli/tests/replay_integration/test_live_headless_ab.py",
    "cli/tests/test_browser_tool_live.py",
    "cli/tests/test_deepseek_reasoner_live.py",
    "cli/tests/test_openai_responses_503_gold_standard_live.py",
    "cli/tests/test_openai_responses_tool_contract_live.py",
    "cli/tests/test_run_multi_llm_live_cases.py",
}

HEAVY_TEST_FILES = {
    "cli/tests/test_app_server_protocol.py",
    "cli/tests/test_app_ui_smoke.py",
    "cli/tests/test_headless_mode.py",
    "cli/tests/test_provider_paths.py",
    "cli/tests/test_provider_status.py",
    "cli/tests/test_runtime_core_modules.py",
    "cli/tests/test_thread_persistence.py",
}

BROWSER_TEST_FILES = {
    "cli/tests/test_gateway_methods_browser.py",
}

POLICY_PLUGIN_TEST_FILES = {
    "cli/tests/test_psbc_policy_plugin.py",
}


def _item_relpath(item) -> str | None:
    raw_path = getattr(item, "path", None)
    if raw_path is None:
        raw_path = getattr(item, "fspath", None)
    if raw_path is None:
        return None
    path = Path(str(raw_path)).resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def _is_browser_test(relpath: str) -> bool:
    return (
        relpath in BROWSER_TEST_FILES
        or relpath.startswith("cli/tests/test_browser_")
        or relpath.startswith("tests/test_web_automation_")
    )


def markers_for_test_path(relpath: str) -> tuple[str, ...]:
    markers: list[str] = []
    if relpath in LIVE_TEST_FILES:
        markers.append("live")
    if relpath in HEAVY_TEST_FILES:
        markers.append("heavy")
    if _is_browser_test(relpath):
        markers.append("browser")
    if relpath in POLICY_PLUGIN_TEST_FILES:
        markers.append("policy_plugin")
    return tuple(markers)


def pytest_collection_modifyitems(config, items) -> None:
    for item in items:
        relpath = _item_relpath(item)
        if not relpath:
            continue
        for marker in markers_for_test_path(relpath):
            item.add_marker(marker)
