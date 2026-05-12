from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_header_helpers import (
    _build_header_family,
    _swap_tools,
)
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_model_helpers import ReplayCase
from cli.scripts.experiments.weather_web_search.replay_weather_header_tool_axes_response_helpers import (
    _classify_result,
    _extract_response_items,
    _parse_event_stream,
)


def _execute_request(
    *,
    url: str,
    request_body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    encoded = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers=headers,
        method="POST",
    )
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            body = response.read()
            content_type = str(response.headers.get("Content-Type") or "")
            status_code = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "http_ok": False,
            "status_code": int(exc.code),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            "error": error_body,
        }
    except Exception as exc:  # pragma: no cover - live-only helper
        return {
            "http_ok": False,
            "status_code": 0,
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }
    text = body.decode("utf-8", errors="replace")
    payloads: list[dict[str, Any]]
    if "text/event-stream" in content_type or text.lstrip().startswith("event:") or text.lstrip().startswith("data:"):
        payloads = _parse_event_stream(text)
    else:
        parsed = json.loads(text)
        payloads = [parsed] if isinstance(parsed, dict) else []
    items, output_text, response_id = _extract_response_items(payloads)
    classification = _classify_result(items, output_text)
    return {
        "http_ok": True,
        "status_code": status_code,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "content_type": content_type,
        "response_id": response_id,
        "payload_count": len(payloads),
        "classification": classification,
    }


def _attempt_path(out_dir: Path, case: ReplayCase, run_index: int) -> Path:
    return out_dir / case.label / f"run_{run_index:02d}.json"


def _run_attempt(
    *,
    case: ReplayCase,
    run_index: int,
    out_dir: Path,
    url: str,
    api_key: str,
    request_bodies: dict[str, dict[str, Any]],
    tool_families: dict[str, list[dict[str, Any]]],
    agenthub_headers: dict[str, str],
    codex_headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    base_request = request_bodies[case.body_family]
    request_body = _swap_tools(base_request, tool_families[case.tool_family])
    headers = _build_header_family(
        family=case.header_family,
        agenthub_headers=agenthub_headers,
        codex_headers=codex_headers,
        api_key=api_key,
    )
    result = _execute_request(
        url=url,
        request_body=request_body,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    attempt_payload = {
        "case": {
            "body_family": case.body_family,
            "header_family": case.header_family,
            "tool_family": case.tool_family,
            "label": case.label,
        },
        "run_index": run_index,
        "request_summary": {
            "model": str(request_body.get("model") or "").strip(),
            "input_count": len(list(request_body.get("input") or [])),
            "tool_count": len(list(request_body.get("tools") or [])),
            "header_keys": sorted(headers),
        },
        "result": result,
    }
    path = _attempt_path(out_dir, case, run_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(attempt_payload, ensure_ascii=False, indent=2))
    return attempt_payload
