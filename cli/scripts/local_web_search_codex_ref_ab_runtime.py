from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from cli.scripts.local_web_search_codex_ref_ab_cases import (
        SearchCase,
        _extract_json_object,
        _host,
        _read_jsonl,
        _text_matches_expected,
        _url_matches_expected,
    )
    from cli.scripts.local_web_search_codex_ref_ab_report import _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from local_web_search_codex_ref_ab_cases import (  # type: ignore[no-redef]
        SearchCase,
        _extract_json_object,
        _host,
        _read_jsonl,
        _text_matches_expected,
        _url_matches_expected,
    )
    from local_web_search_codex_ref_ab_report import _write_text  # type: ignore[no-redef]


def _codex_version(codex_bin: Path) -> str:
    try:
        result = subprocess.run(
            [str(codex_bin), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}: {exc}"
    return (result.stdout or result.stderr or "").strip()


def _run_local_case(case: SearchCase, *, limit: int, fetch_top: bool) -> dict[str, Any]:
    from shared.document_tools.web_search_tools import WebSearchTools

    tools = WebSearchTools()
    started = time.perf_counter()
    payload = tools.web_search(case.query, limit=limit)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    results = [dict(item) for item in list(payload.get("results") or []) if isinstance(item, dict)]
    first_match: dict[str, Any] | None = None
    for item in results:
        url = str(item.get("url") or "")
        if _url_matches_expected(url, case):
            first_match = item
            break
    fetch_payload: dict[str, Any] = {}
    top_url = str((results[0] if results else {}).get("url") or "")
    if fetch_top and top_url:
        fetch_payload = tools.web_fetch(top_url, max_chars=1200)
    return {
        "ok": bool(payload.get("ok")),
        "elapsed_ms": elapsed_ms,
        "count": int(payload.get("count") or 0),
        "engine": str(payload.get("engine") or ""),
        "top_results": [
            {
                "rank": item.get("rank"),
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "source_domain": str(item.get("source_domain") or ""),
                "official_hint": bool(item.get("official_hint")),
                "credibility_label": str(item.get("credibility_label") or ""),
            }
            for item in results[:limit]
        ],
        "expected_hit": first_match is not None,
        "expected_hit_rank": int(first_match.get("rank") or 0) if first_match else None,
        "expected_hit_url": str(first_match.get("url") or "") if first_match else "",
        "fetch_top": (
            {
                "enabled": True,
                "ok": bool(fetch_payload.get("ok")),
                "url": top_url,
                "title": str(fetch_payload.get("title") or ""),
                "blocked_reason": str(fetch_payload.get("blocked_reason") or ""),
                "error": str(fetch_payload.get("error") or ""),
            }
            if fetch_top and top_url
            else {"enabled": bool(fetch_top), "ok": None, "url": top_url}
        ),
        "error": str(payload.get("error") or ""),
    }


def _run_codex_case(
    case: SearchCase,
    *,
    codex_bin: Path,
    model: str,
    reasoning_effort: str,
    sandbox: str,
    timeout_seconds: int,
    out_dir: Path,
) -> dict[str, Any]:
    case_dir = out_dir / case.case_id / "codex_ref"
    workdir = case_dir / "workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    stdout_path = case_dir / "stdout.jsonl"
    stderr_path = case_dir / "stderr.log"
    command = [
        str(codex_bin),
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        sandbox,
        "-C",
        str(workdir),
        "-m",
        model,
    ]
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append(case.prompt)
    started = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        stdout_text = proc.stdout
        stderr_text = proc.stderr
        exit_code = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_text = (
            exc.stdout
            if isinstance(exc.stdout, str)
            else (exc.stdout or b"").decode("utf-8", "replace")
        )
        stderr_text = (
            exc.stderr
            if isinstance(exc.stderr, str)
            else (exc.stderr or b"").decode("utf-8", "replace")
        )
        exit_code = 124
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    _write_text(stdout_path, stdout_text)
    _write_text(stderr_path, stderr_text)
    rows = _read_jsonl(stdout_path)
    assistant_messages: list[str] = []
    web_search_actions: list[dict[str, Any]] = []
    errors: list[str] = []
    usage: dict[str, Any] = {}
    for row in rows:
        if str(row.get("type") or "") == "error" and str(row.get("message") or "").strip():
            errors.append(str(row.get("message") or "").strip())
        if str(row.get("type") or "") == "turn.completed" and isinstance(row.get("usage"), dict):
            usage = dict(row.get("usage") or {})
        item = row.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "") in {"web_search", "web_search_call"}:
            web_search_actions.append(dict(item))
        if str(item.get("type") or "") == "agent_message" and str(item.get("text") or "").strip():
            assistant_messages.append(str(item.get("text") or "").strip())
    assistant_text = assistant_messages[-1] if assistant_messages else ""
    parsed_answer = _extract_json_object(assistant_text)
    answer_url = str(parsed_answer.get("url") or "")
    answer_domain = str(parsed_answer.get("domain") or "") or _host(answer_url)
    expected_hit = _text_matches_expected(
        "\n".join([assistant_text, answer_url, answer_domain]), case
    )
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_ms": elapsed_ms,
        "command": command,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "web_search_call_seen": bool(web_search_actions),
        "web_search_actions": web_search_actions,
        "assistant_text": assistant_text,
        "parsed_answer": parsed_answer,
        "answer_domain": answer_domain,
        "answer_url": answer_url,
        "expected_hit": expected_hit,
        "errors": errors,
        "usage": usage,
    }
