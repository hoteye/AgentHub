from cli.agent_cli.providers import model_catalog_cache_runtime as runtime


def test_update_provider_cache_sets_ttl_and_metadata(tmp_path) -> None:
    cache_path = runtime.default_cache_path(cwd=tmp_path)
    payload = runtime.read_cache(cache_path)
    runtime.update_provider_cache(
        payload,
        provider_name="openai",
        models=[{"model_key": "gpt_54", "model_id": "gpt-5.4"}],
        etag="etag-1",
        last_modified="Fri, 10 Apr 2026 00:00:00 GMT",
        ttl_seconds=120,
        now=1000,
    )
    runtime.write_cache(cache_path, payload)

    loaded = runtime.read_cache(cache_path)
    entry = runtime.provider_cache_entry(loaded, "openai")
    assert entry["etag"] == "etag-1"
    assert entry["last_modified"] == "Fri, 10 Apr 2026 00:00:00 GMT"
    assert entry["fetched_at"] == 1000
    assert entry["expires_at"] == 1120
    assert runtime.cached_models(loaded, provider_name="openai")[0]["model_id"] == "gpt-5.4"

