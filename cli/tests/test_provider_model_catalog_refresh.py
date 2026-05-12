from cli.agent_cli.providers import model_catalog_cache_runtime as cache_runtime
from cli.agent_cli.providers import model_catalog_remote_runtime as remote_runtime


def test_refresh_provider_catalog_cache_falls_back_to_cached_on_remote_error(monkeypatch, tmp_path) -> None:
    cache_path = cache_runtime.default_cache_path(cwd=tmp_path)
    payload = cache_runtime.read_cache(cache_path)
    cache_runtime.update_provider_cache(
        payload,
        provider_name="openai",
        models=[{"model_key": "gpt_54", "model_id": "gpt-5.4"}],
        etag="old-etag",
        ttl_seconds=1,
        now=1,
    )
    cache_runtime.write_cache(cache_path, payload)

    monkeypatch.setattr(
        remote_runtime,
        "fetch_remote_catalog",
        lambda **_: {"status": "error", "error": "network_down"},
    )
    result = remote_runtime.refresh_provider_catalog_cache(
        cache_path=cache_path,
        provider_name="openai",
        catalog_endpoint="https://catalog.example/models",
        force=True,
    )
    assert result["status"] == "fallback_cached"
    assert result["models"][0]["model_id"] == "gpt-5.4"


def test_refresh_provider_catalog_cache_updates_models_when_remote_ok(monkeypatch, tmp_path) -> None:
    cache_path = cache_runtime.default_cache_path(cwd=tmp_path)

    monkeypatch.setattr(
        remote_runtime,
        "fetch_remote_catalog",
        lambda **_: {
            "status": "ok",
            "models": [{"model_key": "gpt_54_mini", "model_id": "gpt-5.4-mini"}],
            "etag": "new-etag",
            "last_modified": "Fri, 10 Apr 2026 00:00:00 GMT",
        },
    )
    result = remote_runtime.refresh_provider_catalog_cache(
        cache_path=cache_path,
        provider_name="openai",
        catalog_endpoint="https://catalog.example/models",
        force=True,
    )
    assert result["status"] == "refreshed"
    assert result["models"][0]["model_id"] == "gpt-5.4-mini"
