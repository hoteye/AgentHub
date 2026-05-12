from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _extract_llm_trace(log_dir: Path) -> dict[str, Any]:
    path = log_dir / "llm_io.jsonl"
    if not path.exists():
        return {"stages": [], "requests": []}
    stages: list[str] = []
    requests: list[dict[str, Any]] = []

    def _provider_name_from_stage(stage_name: str) -> str:
        normalized = str(stage_name or "").strip().lower()
        if normalized.startswith("anthropic_messages."):
            return "anthropic"
        if normalized.startswith("openai_planner.") or normalized.startswith("openai_responses."):
            return "openai"
        return ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        item = json.loads(raw_line)
        stage = str(item.get("stage") or "").strip()
        if not stage:
            continue
        stages.append(stage)
        payload = item.get("payload") or {}
        request = payload.get("request") if isinstance(payload, dict) else None
        response = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(request, dict) and not isinstance(response, dict):
            continue
        provider_name = str(payload.get("provider_name") or "").strip() or _provider_name_from_stage(stage)
        model = ""
        message_count = 0
        if isinstance(request, dict):
            model = str(request.get("model") or payload.get("model") or "").strip()
            messages = request.get("messages")
            if isinstance(messages, list):
                message_count = len(messages)
            elif isinstance(request.get("input"), list):
                message_count = len(list(request.get("input") or []))
        if not model and isinstance(response, dict):
            model = str(response.get("model") or payload.get("model") or "").strip()
        requests.append(
            {
                "stage": stage,
                "route_name": str(payload.get("route_name") or "").strip(),
                "route_source": str(payload.get("route_source") or "").strip(),
                "provider_name": provider_name,
                "base_url": str(payload.get("base_url") or "").strip(),
                "model": model,
                "message_count": message_count,
            }
        )
    return {"stages": stages, "requests": requests}
