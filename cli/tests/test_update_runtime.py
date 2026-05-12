from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import update_runtime
from cli.agent_cli.runtime_core.command_handlers import handle_known_command


def test_normalize_release_version_strips_supported_tag_prefixes() -> None:
    assert update_runtime.normalize_release_version("v1.2.3") == "1.2.3"
    assert update_runtime.normalize_release_version("cli-v1.2.3") == "1.2.3"
    assert update_runtime.normalize_release_version("agenthub-v1.2.3") == "1.2.3"


def test_is_newer_version_compares_semver_tags() -> None:
    assert update_runtime.is_newer_version("v1.2.4", "1.2.3") is True
    assert update_runtime.is_newer_version("1.2.3", "1.2.3") is False
    assert update_runtime.is_newer_version("not-a-version", "1.2.3") is False


def test_cache_is_stale_when_missing_or_older_than_interval() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    assert update_runtime.cache_is_stale({}, now=now, interval_seconds=60) is True
    assert (
        update_runtime.cache_is_stale(
            {"last_checked_at": "2026-04-26T09:58:00+00:00"},
            now=now,
            interval_seconds=60,
        )
        is True
    )
    assert (
        update_runtime.cache_is_stale(
            {"last_checked_at": "2026-04-26T09:59:30+00:00"},
            now=now,
            interval_seconds=60,
        )
        is False
    )


def test_update_status_reports_disabled_when_latest_url_is_unconfigured(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AGENTHUB_UPDATE_LATEST_URL", raising=False)
    monkeypatch.delenv("AGENTHUB_UPDATE_MANIFEST_URL", raising=False)
    monkeypatch.setenv("AGENTHUB_UPDATE_CACHE_PATH", str(tmp_path / "version.json"))

    text = update_runtime.update_status_text()

    assert "update status" in text
    assert "check_enabled=false" in text
    assert "latest_version=-" in text
    assert "next_action=set AGENTHUB_UPDATE_LATEST_URL after publishing GitHub releases" in text


def test_refresh_update_cache_writes_latest_version(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "version.json"
    monkeypatch.setenv("AGENTHUB_UPDATE_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("AGENTHUB_UPDATE_LATEST_URL", "https://updates.example/latest.json")

    with patch("cli.agent_cli.update_runtime.fetch_latest_version", return_value="0.2.0"):
        payload = update_runtime.refresh_update_cache()

    assert payload["latest_version"] == "0.2.0"
    assert update_runtime.read_update_cache(cache_path)["latest_version"] == "0.2.0"


def test_cached_update_notice_requires_configured_update_url(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "version.json"
    update_runtime.write_update_cache({"latest_version": "0.2.0"}, cache_path)
    monkeypatch.setenv("AGENTHUB_UPDATE_CACHE_PATH", str(cache_path))
    monkeypatch.delenv("AGENTHUB_UPDATE_LATEST_URL", raising=False)
    monkeypatch.delenv("AGENTHUB_UPDATE_MANIFEST_URL", raising=False)

    assert update_runtime.cached_update_notice() == ""

    monkeypatch.setenv("AGENTHUB_UPDATE_LATEST_URL", "https://updates.example/latest.json")
    assert "AgentHub update available: 0.1.0 -> 0.2.0" in update_runtime.cached_update_notice()


def test_dismiss_cached_update_marks_latest_version(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "version.json"
    update_runtime.write_update_cache({"latest_version": "0.2.0"}, cache_path)
    monkeypatch.setenv("AGENTHUB_UPDATE_CACHE_PATH", str(cache_path))

    cache = update_runtime.dismiss_cached_update()

    assert cache["dismissed_version"] == "0.2.0"
    assert update_runtime.read_update_cache(cache_path)["dismissed_version"] == "0.2.0"


def test_update_command_status_and_dismiss_use_update_runtime(tmp_path, monkeypatch) -> None:
    cache_path = tmp_path / "version.json"
    update_runtime.write_update_cache({"latest_version": "0.2.0"}, cache_path)
    monkeypatch.setenv("AGENTHUB_UPDATE_CACHE_PATH", str(cache_path))
    monkeypatch.setenv("AGENTHUB_UPDATE_LATEST_URL", "https://updates.example/latest.json")
    runtime = SimpleNamespace(_is_interrupt_requested=lambda: False)

    status = handle_known_command(runtime, name="update", arg_text="status", text="/update status")
    dismiss = handle_known_command(runtime, name="update", arg_text="dismiss", text="/update dismiss")

    assert status is not None
    assert dismiss is not None
    assert "update_available=true" in status[0]
    assert "update dismissed" in dismiss[0]
    assert update_runtime.read_update_cache(cache_path)["dismissed_version"] == "0.2.0"
