from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Mapping

from cli.agent_cli.gateway_server.dispatcher import dispatch_gateway_method
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_factory import build_persistent_runtime
from .webhook_api import verify_webhook_signature


def process_github_webhook(
    runtime: AgentCliRuntime,
    *,
    headers: Mapping[str, Any],
    raw_body: bytes,
    webhook_secret: str | None = None,
) -> tuple[int, dict[str, Any]]:
    if webhook_secret:
        verified = verify_webhook_signature(
            headers=dict(headers),
            raw_body=raw_body,
            secret=webhook_secret,
            header_name="X-Hub-Signature-256",
            prefix="sha256=",
        )
        if not verified:
            return 401, {"ok": False, "error": "invalid_signature"}
    outcome = dispatch_gateway_method(
        method="github.webhook.ingest",
        params={
            "connectorKey": "github_webhook",
            "rawBody": raw_body.decode("utf-8"),
            "headers": dict(headers),
        },
        runtime=runtime,
        request_id=str(dict(headers).get("X-GitHub-Delivery") or "github-webhook"),
        client_info={
            "gatewayAuth": {
                "actorId": "github-webhook",
                "role": "webhook",
                "scopes": ["github.read"],
                "authSource": "github_http_server",
                "trustLevel": "external",
                "authenticated": True,
                "clientType": "http_webhook",
            }
        },
    )
    if not outcome.ok:
        if int(outcome.error_code or 0) == -32602:
            return 400, {"ok": False, "error": str((outcome.error_data or {}).get("detail") or "invalid_request")}
        return 500, {
            "ok": False,
            "error": str(outcome.error_message or "github_webhook_dispatch_failed"),
            "details": dict(outcome.error_data or {}),
        }
    result = dict(outcome.result or {})
    event = dict(result.get("event") or {})
    decision = dict(result.get("decision") or {})
    workflow_run = dict(result.get("workflowRun") or {})
    return 202, {
        "ok": True,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "trace_id": event.get("trace_id"),
        "correlation_id": event.get("correlation_id"),
        "target_kind": decision.get("targetKind"),
        "plugin_name": decision.get("pluginName"),
        "workflow_name": decision.get("workflowName"),
        "workflow_run_id": workflow_run.get("workflow_run_id"),
    }


class GitHubWebhookHandler(BaseHTTPRequestHandler):
    runtime: AgentCliRuntime | None = None
    webhook_secret: str | None = None

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/webhooks/github":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        content_length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(content_length)
        runtime = type(self).runtime or build_persistent_runtime()
        status, payload = process_github_webhook(
            runtime,
            headers=dict(self.headers.items()),
            raw_body=raw_body,
            webhook_secret=type(self).webhook_secret,
        )
        self._send_json(status, payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_github_webhook_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    runtime: AgentCliRuntime | None = None,
    webhook_secret: str | None = None,
) -> int:
    handler = type(
        "BoundGitHubWebhookHandler",
        (GitHubWebhookHandler,),
        {
            "runtime": runtime or build_persistent_runtime(),
            "webhook_secret": webhook_secret,
        },
    )
    server = HTTPServer((host, int(port)), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub Phase 1 webhook HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--webhook-secret-env", default="GITHUB_WEBHOOK_SECRET")
    args = parser.parse_args(argv)
    secret_env = str(args.webhook_secret_env or "GITHUB_WEBHOOK_SECRET").strip() or "GITHUB_WEBHOOK_SECRET"
    return run_github_webhook_server(
        host=str(args.host),
        port=int(args.port),
        webhook_secret=str(os.environ.get(secret_env) or "").strip() or None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
