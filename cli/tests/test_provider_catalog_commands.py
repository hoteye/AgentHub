from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import cli.agent_cli.runtime_core.provider_catalog_commands_runtime as provider_catalog_commands_runtime
from cli.agent_cli import provider_catalog_runtime
from cli.agent_cli.providers import model_catalog_cache_runtime
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command


def _parse_args(arg_text: str):
    text = str(arg_text or "").strip()
    tokens = text.split() if text else []
    positionals: list[str] = []
    options: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key = token[2:]
            value: object = True
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                value = tokens[index + 1]
                index += 1
            options[key] = value
        else:
            positionals.append(token)
        index += 1
    return positionals, options


def _switch_disabled_result(exc: Exception) -> tuple[str, list[object]]:
    return str(exc), []


def _runtime_stub(
    *,
    cwd: Path,
    catalog: SimpleNamespace,
    provider_items: list[dict[str, str]] | None = None,
) -> SimpleNamespace:
    class _FakeAgent:
        @staticmethod
        def _load_provider_catalog(**kwargs):
            del kwargs
            return catalog

        @staticmethod
        def _provider_loader_kwargs() -> dict[str, object]:
            return {"cwd": cwd}

        @staticmethod
        def _supplement_provider_catalog(input_catalog):
            return input_catalog

        @staticmethod
        def available_providers():
            return list(provider_items or [])

    return SimpleNamespace(
        cwd=str(cwd),
        _parse_args=_parse_args,
        agent=_FakeAgent(),
    )


def _catalog_with_providers(provider_names: list[str]) -> SimpleNamespace:
    providers = {
        name: SimpleNamespace(
            raw_provider={"catalog_endpoint": f"https://catalog.example/{name}.json"}
        )
        for name in provider_names
    }
    return SimpleNamespace(providers=providers)


def test_models_refresh_with_provider_filter_uses_mocked_remote_refresh(monkeypatch, tmp_path: Path) -> None:
    catalog = _catalog_with_providers(["openai", "glm"])
    runtime = _runtime_stub(cwd=tmp_path, catalog=catalog)
    cache_path = tmp_path / ".agent_cli" / "model_catalog_cache.json"
    refresh_calls: list[tuple[str, str]] = []

    def _refresh_remote_model_catalog(*, provider_name: str, catalog_endpoint: str, **kwargs):
        del kwargs
        refresh_calls.append((provider_name, catalog_endpoint))
        return {
            "status": "refreshed",
            "cache_hit": False,
            "models": [{"model_id": "gpt-5.4"}],
        }

    monkeypatch.setattr(
        provider_catalog_runtime,
        "refresh_remote_model_catalog",
        _refresh_remote_model_catalog,
    )
    monkeypatch.setattr(
        provider_catalog_runtime,
        "remote_model_catalog_cache_path",
        lambda **_: cache_path,
        raising=False,
    )

    result = handle_provider_command(
        runtime,
        name="models_refresh",
        arg_text="openai",
        switch_disabled_result=_switch_disabled_result,
    )

    assert result is not None, "models_refresh command is not registered"
    text, events = result
    assert events == []
    assert refresh_calls == [("openai", "https://catalog.example/openai.json")]
    assert "cache_path=" in text
    assert re.search(r"(?mi)^.*openai.*$", text)
    assert "refreshed" in text.lower()


def test_models_refresh_unknown_provider_returns_clear_error_and_usage(tmp_path: Path) -> None:
    runtime = _runtime_stub(
        cwd=tmp_path,
        catalog=_catalog_with_providers(["openai", "glm"]),
    )

    result = handle_provider_command(
        runtime,
        name="models_refresh",
        arg_text="unknown_provider",
        switch_disabled_result=_switch_disabled_result,
    )

    assert result is not None, "models_refresh command is not registered"
    text, events = result
    assert events == []
    assert "provider not found" in text.lower()
    assert "/models_refresh" in text


def test_models_cache_status_reports_missing_stale_fresh_and_includes_cache_path(monkeypatch, tmp_path: Path) -> None:
    runtime = _runtime_stub(
        cwd=tmp_path,
        catalog=_catalog_with_providers(["fresh_provider", "stale_provider", "missing_provider"]),
    )
    now = 1_800_000_000
    cache_path = tmp_path / ".agent_cli" / "model_catalog_cache.json"
    cached_payload = {
        "providers": {
            "fresh_provider": {
                "provider": "fresh_provider",
                "models": [{"model_id": "fresh-1"}],
                "fetched_at": now - 60,
                "expires_at": now + 3600,
            },
            "stale_provider": {
                "provider": "stale_provider",
                "models": [{"model_id": "stale-1"}],
                "fetched_at": now - 7200,
                "expires_at": now - 1,
            },
        }
    }

    monkeypatch.setattr(
        model_catalog_cache_runtime,
        "default_cache_path",
        lambda **_: cache_path,
    )
    monkeypatch.setattr(
        model_catalog_cache_runtime,
        "read_cache",
        lambda _path: cached_payload,
    )
    monkeypatch.setattr(
        provider_catalog_commands_runtime.time,
        "time",
        lambda: float(now),
    )

    result = handle_provider_command(
        runtime,
        name="models_cache_status",
        arg_text="",
        switch_disabled_result=_switch_disabled_result,
    )

    assert result is not None, "models_cache_status command is not registered"
    text, events = result
    assert events == []
    assert "cache_path=" in text
    assert str(cache_path) in text
    assert re.search(r"(?mi)^.*fresh_provider.*fresh.*$", text)
    assert re.search(r"(?mi)^.*stale_provider.*stale.*$", text)
    assert re.search(r"(?mi)^.*missing_provider.*missing.*$", text)
