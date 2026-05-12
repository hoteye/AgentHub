from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.providers.wellknown_discovery_runtime import discover_wellknown_metadata


class ProviderWellknownDiscoveryRuntimeTest(unittest.TestCase):
    def test_discovery_from_issuer_persists_cache_and_uses_min_ttl(self) -> None:
        observed_urls: list[str] = []

        def _http_client(**kwargs):
            observed_urls.append(str(kwargs.get("url") or ""))
            return {
                "status_code": 200,
                "body": json.dumps(
                    {
                        "issuer": "https://issuer.example",
                        "token_endpoint": "https://issuer.example/oauth/token",
                        "device_authorization_endpoint": "https://issuer.example/oauth/device/code",
                    }
                ),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "wellknown_cache.json"
            result = discover_wellknown_metadata(
                cache_path=cache_path,
                issuer="https://issuer.example/",
                ttl_seconds=10,
                now_ts=1_800_000_000.0,
                http_client=_http_client,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                observed_urls,
                ["https://issuer.example/.well-known/openid-configuration"],
            )
            self.assertEqual(result["fetched_at"], 1_800_000_000)
            self.assertEqual(result["expires_at"], 1_800_000_060)  # ttl min 60
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertTrue(isinstance(payload.get("entries"), dict))
            self.assertEqual(len(payload["entries"]), 1)

    def test_discovery_prefers_metadata_url(self) -> None:
        observed_urls: list[str] = []

        def _http_client(**kwargs):
            observed_urls.append(str(kwargs.get("url") or ""))
            return {
                "status_code": 200,
                "body": json.dumps(
                    {
                        "issuer": "https://issuer.example",
                        "token_endpoint": "https://issuer.example/oauth/token",
                    }
                ),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "wellknown_cache.json"
            result = discover_wellknown_metadata(
                cache_path=cache_path,
                issuer="https://ignored.example",
                metadata_url="https://metadata.example/openid-configuration",
                now_ts=1_800_000_000.0,
                http_client=_http_client,
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(observed_urls, ["https://metadata.example/openid-configuration"])
        self.assertEqual(result["metadata_url"], "https://metadata.example/openid-configuration")

    def test_remote_failure_returns_fallback_cached_when_not_expired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "wellknown_cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "entries": {
                            "issuer::https://issuer.example": {
                                "fetched_at": 1_800_000_000,
                                "expires_at": 1_800_000_100,
                                "issuer": "https://issuer.example",
                                "token_endpoint": "https://issuer.example/oauth/token",
                                "device_authorization_endpoint": "https://issuer.example/oauth/device/code",
                                "metadata_url": "https://issuer.example/.well-known/openid-configuration",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = discover_wellknown_metadata(
                cache_path=cache_path,
                issuer="https://issuer.example",
                now_ts=1_800_000_050.0,
                http_client=lambda **kwargs: {"error": "network:timeout"},
            )

        self.assertEqual(result["status"], "fallback_cached")
        self.assertEqual(result["issuer"], "https://issuer.example")
        self.assertEqual(result["error"], "network:timeout")

    def test_remote_failure_returns_error_when_cache_expired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "wellknown_cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "entries": {
                            "issuer::https://issuer.example": {
                                "fetched_at": 1_800_000_000,
                                "expires_at": 1_800_000_010,
                                "issuer": "https://issuer.example",
                                "token_endpoint": "https://issuer.example/oauth/token",
                                "device_authorization_endpoint": "https://issuer.example/oauth/device/code",
                                "metadata_url": "https://issuer.example/.well-known/openid-configuration",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = discover_wellknown_metadata(
                cache_path=cache_path,
                issuer="https://issuer.example",
                now_ts=1_800_000_050.0,
                http_client=lambda **kwargs: {"status_code": 503, "body": "upstream down"},
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "http_503")

