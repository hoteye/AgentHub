from __future__ import annotations

import json
from pathlib import Path

from cli.agent_cli.host.plugin_installation_state import PluginInstallationStore


def test_installation_store_upsert_and_remove_scope_entries(tmp_path: Path) -> None:
    store = PluginInstallationStore(tmp_path / "installed_plugins.json")

    first = store.upsert_installation(
        "sample@test",
        scope="user",
        install_path="/tmp/sample-user",
        version="1.0.0",
        source_kind="dir",
    )
    second = store.upsert_installation(
        "sample@test",
        scope="project",
        install_path="/tmp/sample-project",
        version="1.0.1",
        source_kind="zip",
    )

    assert first.scope == "user"
    assert second.scope == "project"
    assert store.has_installation("sample@test", scope="user") is True
    assert store.has_installation("sample@test", scope="project") is True

    removed = store.remove_installations("sample@test", scope="project")
    assert [item.scope for item in removed] == ["project"]
    assert store.has_installation("sample@test", scope="project") is False
    assert store.has_installation("sample@test", scope="user") is True

    removed_all = store.remove_installations("sample@test")
    assert [item.scope for item in removed_all] == ["user"]
    assert store.has_installation("sample@test") is False


def test_installation_store_ignores_invalid_rows_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "good@test": [
                        {
                            "scope": "user",
                            "installPath": "/tmp/good",
                            "version": "1.2.3",
                        }
                    ],
                    "bad-key": [{"scope": "user", "installPath": "/tmp/bad"}],
                    "bad-entry@test": [{"scope": "oops", "installPath": "/tmp/bad-entry"}],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    store = PluginInstallationStore(path)
    loaded = store.list_installations()

    assert sorted(loaded.keys()) == ["good@test"]
    assert loaded["good@test"][0].install_path == "/tmp/good"

