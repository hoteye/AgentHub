from __future__ import annotations


def operator_pipe_segments(raw_line: str) -> list[str]:
    line = str(raw_line or "").strip()
    if not line.startswith("- "):
        return []
    return [segment.strip() for segment in line[2:].split(" | ") if segment.strip()]


def operator_segment_map(segments: list[str]) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    keyed: dict[str, str] = {}
    for segment in list(segments or []):
        if "=" in segment:
            key, value = segment.split("=", 1)
            keyed[str(key).strip()] = str(value).strip()
        else:
            positional.append(str(segment).strip())
    return positional, keyed


def prefixed_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split(":", 1)[0].strip()


def workflow_detail_identity(keyed: dict[str, str]) -> tuple[str, str, str]:
    card = str(keyed.get("card") or "").strip()
    task = str(keyed.get("task") or "").strip()
    action = str(keyed.get("action") or "").strip()
    if not card:
        for key in ("current", "current_result", "latest_acceptance", "latest", "blocker", "review_reason"):
            card = prefixed_token(keyed.get(key, ""))
            if card:
                break
    if not task:
        for key in ("dispatch_ref", "dispatch_refs", "execution_ref", "execution_refs", "result_ref"):
            candidate = str(keyed.get(key) or "").strip()
            if not candidate:
                continue
            if "," in candidate:
                candidate = candidate.split(",", 1)[0].strip()
            parts = [part.strip() for part in candidate.split(":") if part.strip()]
            if len(parts) >= 3:
                task = parts[-1]
                break
    if not action:
        for key in ("review_action", "next_action", "workflow_action", "next", "wait"):
            candidate = str(keyed.get(key) or "").strip()
            if candidate:
                action = candidate
                break
    return (card, task, action)
