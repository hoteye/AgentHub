from __future__ import annotations

from cli.agent_cli.runtime_kernels.base import StartTurnRequest
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject


def _turn_input_items(request: StartTurnRequest) -> list[JsonObject]:
    if request.input_items:
        return [dict(item) for item in request.input_items]
    return [
        {
            "type": "text",
            "text": request.text,
            "textElements": [],
        }
    ]


def _turn_id_from_result(result: JsonObject) -> str:
    turn = result.get("turn")
    if isinstance(turn, dict):
        return str(turn.get("id") or turn.get("turnId") or "")
    return str(result.get("turnId") or "")
