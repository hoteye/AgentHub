from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

from tools.psbc_audit_case_eval_model_helpers import (
    AuditCase,
    DraftResult,
    _dedupe,
    _extract_responsibility_subjects,
    _issue_label,
    _pick_evidence_lines,
    _query_terms,
    _shorten,
    _split_evidence_lines,
)


def _provider_wire_mode() -> str:
    from cli.agent_cli.provider import load_provider_config

    config = load_provider_config()
    if config is None:
        return "unavailable"
    wire_api = str(config.wire_api or "").strip().lower()
    planner_kind = str(config.planner_kind or "").strip().lower()
    if wire_api == "responses" or planner_kind == "openai_responses":
        return "responses"
    return "chat"


def _extract_json_payload(raw_text: str) -> tuple[Dict[str, Any] | None, str | None]:
    text = str(raw_text or "").strip()
    if not text:
        return None, "empty_response"
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None, f"json_parse_failed: {exc.msg}"
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as nested_exc:
            return None, f"json_parse_failed: {nested_exc.msg}"
    if not isinstance(payload, dict):
        return None, f"unexpected_json_type: {type(payload).__name__}"
    return payload, None


def _format_llm_error(exc: Exception) -> str:
    name = type(exc).__name__
    message = str(exc).strip()
    return f"{name}: {message}" if message else name


def _retryable_llm_error(exc: Exception) -> bool:
    try:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
    except Exception:
        retryable_types: tuple[type[Exception], ...] = ()
    else:
        retryable_types = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

    if retryable_types and isinstance(exc, retryable_types):
        return True
    message = _format_llm_error(exc).lower()
    return "429" in message or "rate limit" in message or "timeout" in message


def _llm_text(system_prompt: str, user_prompt: str, *, max_attempts: int = 3) -> tuple[str | None, str | None]:
    from cli.agent_cli.provider import load_provider_config

    config = load_provider_config()
    if config is None or not str(config.api_key or "").strip() or not str(config.model or "").strip():
        return None, "provider_config_unavailable"

    try:
        from openai import OpenAI
    except Exception as exc:
        return None, _format_llm_error(exc)

    client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=30.0)
    mode = _provider_wire_mode()
    last_error = "llm_request_not_attempted"
    for attempt in range(1, max_attempts + 1):
        try:
            if mode == "responses":
                kwargs: Dict[str, Any] = {
                    "model": config.model,
                    "instructions": system_prompt,
                    "input": [{"role": "user", "content": user_prompt}],
                    "store": False,
                    "stream": True,
                }
                if config.reasoning_effort:
                    kwargs["reasoning"] = {"effort": config.reasoning_effort}
                stream = client.responses.create(**kwargs)
                text_parts: List[str] = []
                for event in stream:
                    event_type = getattr(event, "type", "")
                    if event_type in {"response.output_text.delta", "response.refusal.delta"}:
                        delta = getattr(event, "delta", "")
                        if delta:
                            text_parts.append(str(delta))
                text = "".join(text_parts).strip()
                if text:
                    return text, None
                last_error = "empty_response_text"
            else:
                response = client.chat.completions.create(
                    model=config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                message = response.choices[0].message
                content = getattr(message, "content", "")
                if isinstance(content, str):
                    text = content.strip()
                elif isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(str(item.get("text") or ""))
                        else:
                            text_parts.append(str(getattr(item, "text", "") or ""))
                    text = "".join(text_parts).strip()
                else:
                    text = str(content or "").strip()
                if text:
                    return text, None
                last_error = "empty_response_text"
        except Exception as exc:
            last_error = _format_llm_error(exc)
            if attempt >= max_attempts or not _retryable_llm_error(exc):
                return None, last_error
            time.sleep(min(2 ** (attempt - 1), 6))
            continue
        if attempt >= max_attempts:
            return None, last_error
        time.sleep(min(2 ** (attempt - 1), 6))
    return None, last_error


def _evidence_prompt_blocks(case: AuditCase, evidence_docs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence_terms = _query_terms(case.finding, case.question, case.live_query)
    responsibility_terms = [
        "责任部门",
        "安全管理员",
        "外包执行部门",
        "建设单位",
        "业务部门",
        "金融科技部",
        "运营数据中心",
        "系统管理员",
        "堡垒用户",
    ]
    blocks: List[Dict[str, Any]] = []
    for item in evidence_docs[:3]:
        title = str((item.get("document") or {}).get("title") or item.get("title") or "").strip()
        text = str(item.get("text") or "")
        if not text:
            continue
        lines = _pick_evidence_lines(text, [*evidence_terms, *responsibility_terms], limit=6)
        if not lines:
            continue
        blocks.append({"title": title or "命中文档", "lines": lines[:6]})
    return blocks


def _llm_draft_answer(case: AuditCase, evidence_docs: Sequence[Dict[str, Any]]) -> tuple[DraftResult | None, str | None]:
    blocks = _evidence_prompt_blocks(case, evidence_docs)
    if not blocks:
        return None, "insufficient_evidence_blocks"
    system_prompt = (
        "你是邮储制度审计验证助手。"
        "你的任务不是自由发挥，而是只根据提供的制度证据，起草一个尽量贴近审计定性的话术。"
        "优先输出制度义务、问题定性、责任主体。"
        "如果证据不足，就明确写证据不足，不要编造。"
        "返回严格 JSON，不要 markdown，不要解释。"
        "JSON keys: issue_label, responsibility_subjects, answer_text."
    )
    evidence_lines: List[str] = []
    for index, block in enumerate(blocks, start=1):
        evidence_lines.append(f"[证据{index}] {block['title']}")
        for line in block["lines"]:
            evidence_lines.append(f"- {line}")
    user_prompt = "\n".join(
        [
            f"审计发现: {case.finding}",
            f"审计问题: {case.question}",
            f"检索查询: {case.live_query}",
            "证据如下:",
            *evidence_lines,
            (
                "请输出一个带固定段落标题的中文答案，answer_text 必须严格采用以下结构：\n"
                "问题定性：\\n- ...\\n责任环节：\\n- ...\\n制度依据：\\n- 文档标题: 条款..."
            ),
        ]
    )
    raw_text, llm_error = _llm_text(system_prompt, user_prompt)
    if raw_text is None:
        return None, llm_error or "empty_response_text"
    payload, payload_error = _extract_json_payload(raw_text)
    if payload is None:
        shortened = _shorten(raw_text, limit=220)
        detail = payload_error or "json_parse_failed"
        return None, f"{detail}; raw={shortened}"
    answer_text = str(payload.get("answer_text") or "").strip()
    if not answer_text:
        return None, "missing_answer_text"
    responsibility_subjects = payload.get("responsibility_subjects") or []
    if not isinstance(responsibility_subjects, list):
        responsibility_subjects = []
    evidence_titles = [
        str((item.get("document") or {}).get("title") or item.get("title") or Path(str(item.get("markdown_path") or "")).name)
        for item in evidence_docs
    ]
    evidence_lines_flat = [line for block in blocks for line in block["lines"]][:6]
    return (
        DraftResult(
            mode="llm",
            answer={
                "answer_text": answer_text,
                "issue_label": str(payload.get("issue_label") or "").strip() or _issue_label(answer_text),
                "responsibility_subjects": _dedupe(str(item) for item in responsibility_subjects)[:5],
                "evidence_titles": evidence_titles,
                "evidence_lines": evidence_lines_flat,
            },
        ),
        None,
    )


def _heuristic_draft_answer(case: AuditCase, evidence_docs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    evidence_text = "\n".join(str(item.get("text") or "") for item in evidence_docs)
    evidence_titles = [
        str((item.get("document") or {}).get("title") or item.get("title") or Path(str(item.get("markdown_path") or "")).name)
        for item in evidence_docs
    ]
    evidence_terms = _query_terms(case.finding, case.question, case.live_query)
    evidence_lines = _pick_evidence_lines(evidence_text, evidence_terms, limit=4)
    responsibility_terms = [
        "责任部门",
        "安全管理员",
        "外包执行部门",
        "建设单位",
        "业务部门",
        "金融科技部",
        "运营数据中心",
        "系统管理员",
        "堡垒用户",
    ]
    responsibility_lines = _pick_evidence_lines(evidence_text, responsibility_terms, limit=4)
    responsibility_subjects = _extract_responsibility_subjects([*evidence_lines, *responsibility_lines])
    explicit_responsibility_lines = [
        line
        for line in _split_evidence_lines(evidence_text)
        if any(
            keyword in line
            for keyword in (
                "责任部门",
                "安全管理员",
                "外包执行部门",
                "金融科技部",
                "建设单位",
                "业务部门",
                "运营数据中心",
                "系统管理员",
                "堡垒用户",
            )
        )
    ]
    explicit_responsibility_lines = _dedupe(explicit_responsibility_lines)
    explicit_responsibility_lines.sort(
        key=lambda line: (
            -(
                ("责任部门" in line) * 6
                + ("外包执行部门" in line) * 5
                + ("建设单位" in line) * 5
                + ("金融科技部" in line) * 4
                + ("运营数据中心" in line) * 4
                + ("安全管理员" in line) * 4
                + ("系统管理员" in line) * 3
                + ("堡垒用户" in line) * 2
            ),
            len(line),
        )
    )
    explicit_responsibility_lines = explicit_responsibility_lines[:4]
    label = _issue_label("\n".join([case.finding, evidence_text]))
    obligation_summary = _shorten(evidence_lines[0] if evidence_lines else case.finding, limit=120)

    lines: List[str] = [
        "问题定性：",
        f"- 根据命中的制度证据，该问题可定性为{label}，核心偏差是未按制度要求落实“{obligation_summary}”。",
        "责任环节：",
    ]
    if responsibility_subjects:
        for item in responsibility_subjects:
            lines.append(f"- {item}")
        for item in explicit_responsibility_lines[:2]:
            if item not in "\n".join(lines):
                lines.append(f"- {item}")
    elif explicit_responsibility_lines:
        for item in explicit_responsibility_lines[:3]:
            lines.append(f"- {item}")
    else:
        lines.append("- 责任主体未从命中文本中稳定抽取，需结合审计底稿人工确认。")
    lines.append("制度依据：")
    if evidence_lines:
        if len(evidence_titles) <= 1:
            title = evidence_titles[0] if evidence_titles else "命中文档"
            for line in evidence_lines[:3]:
                lines.append(f"- {title}: {line}")
        else:
            for title, line in zip(evidence_titles, evidence_lines):
                lines.append(f"- {title}: {line}")
    else:
        for title in evidence_titles[:3]:
            lines.append(f"- {title}")

    return {
        "answer_text": "\n".join(lines),
        "issue_label": label,
        "responsibility_subjects": responsibility_subjects,
        "evidence_titles": evidence_titles,
        "evidence_lines": evidence_lines,
    }


def _draft_answer(case: AuditCase, evidence_docs: Sequence[Dict[str, Any]], *, draft_mode: str = "heuristic") -> DraftResult:
    normalized_mode = str(draft_mode or "heuristic").strip().lower()
    llm_error: str | None = None
    if normalized_mode == "llm":
        llm_result, llm_error = _llm_draft_answer(case, evidence_docs)
        if llm_result is not None:
            return llm_result
    heuristic = _heuristic_draft_answer(case, evidence_docs)
    return DraftResult(answer=heuristic, mode="heuristic", fallback_reason=llm_error if normalized_mode == "llm" else None)
