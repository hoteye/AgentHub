from __future__ import annotations

import re
from typing import Any, Dict, Optional


def analyze_send_risk(draft_text: Optional[str], conversation_name: Optional[str]) -> Dict[str, Any]:
    text = (draft_text or "").strip()
    normalized = text.lower()
    findings = []

    rules = [
        {
            "label": "credential_or_secret",
            "level": "high",
            "blocked": True,
            "patterns": [
                r"密码",
                r"口令",
                r"验证码",
                r"密钥",
                r"token",
                r"secret",
                r"apikey",
                r"api\s*key",
                r"private\s*key",
                r"password",
            ],
            "message": "草稿里包含疑似凭据、验证码或密钥信息，默认禁止自动发送。",
        },
        {
            "label": "personal_sensitive_data",
            "level": "high",
            "blocked": True,
            "patterns": [
                r"身份证",
                r"银行卡",
                r"\b\d{15,19}\b",
            ],
            "message": "草稿里包含疑似高敏个人信息，默认禁止自动发送。",
        },
        {
            "label": "funds_or_invoice",
            "level": "medium",
            "blocked": False,
            "patterns": [
                r"转账",
                r"汇款",
                r"付款",
                r"打款",
                r"报销",
                r"发票",
                r"payment",
                r"invoice",
                r"transfer",
                r"wire",
            ],
            "message": "草稿涉及资金或票据信息，建议人工复核金额、对象和时间。",
        },
        {
            "label": "strong_commitment",
            "level": "medium",
            "blocked": False,
            "patterns": [
                r"保证",
                r"承诺",
                r"确保",
                r"马上处理",
                r"立即完成",
                r"guarantee",
                r"promise",
                r"commit",
                r"immediately",
            ],
            "message": "草稿包含较强承诺性措辞，建议人工复核责任边界和截止时间。",
        },
    ]

    for rule in rules:
        matched_keywords = []
        for pattern in rule["patterns"]:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                matched_keywords.append(pattern)
        if matched_keywords:
            findings.append(
                {
                    "label": rule["label"],
                    "level": rule["level"],
                    "blocked": rule["blocked"],
                    "message": rule["message"],
                    "matched_keywords": matched_keywords,
                }
            )

    if len(text) < 4:
        findings.append(
            {
                "label": "text_too_short",
                "level": "medium",
                "blocked": False,
                "message": "草稿内容过短，建议确认是否缺少上下文或称呼。",
                "matched_keywords": [],
            }
        )

    if not conversation_name:
        findings.append(
            {
                "label": "conversation_not_explicit",
                "level": "medium",
                "blocked": False,
                "message": "当前没有明确会话名称，建议先确认发送对象。",
                "matched_keywords": [],
            }
        )

    level_rank = {"low": 0, "medium": 1, "high": 2}
    risk_level = "low"
    for finding in findings:
        if level_rank[finding["level"]] > level_rank[risk_level]:
            risk_level = finding["level"]

    blocked = any(item["blocked"] for item in findings)
    summary = "未发现明显风险。"
    if findings:
        summary = "；".join(item["message"] for item in findings[:3])
    return {
        "risk_level": risk_level,
        "blocked": blocked,
        "finding_count": len(findings),
        "findings": findings,
        "summary": summary,
    }


def approval_message(risk_guard: Dict[str, Any]) -> str:
    risk_level = risk_guard.get("risk_level") or "low"
    blocked = bool(risk_guard.get("blocked"))
    if blocked:
        return "发送已被风险审查拦截，请先修改草稿。"
    if risk_level == "medium":
        return "草稿已准备，但存在中风险提示，请人工复核后再确认发送。"
    return "草稿已准备完成，可以确认发送。"


def recovery_suggestions(operation: str, result: Dict[str, Any]) -> list[str]:
    reason = (result.get("reason") or "").strip()
    suggestions = []

    if operation in {"prepare_send", "send_reply"}:
        if reason == "send_blocked_by_risk_guard":
            suggestions.append("先修改草稿中的敏感信息，再重新准备发送。")
        if reason in {"conversation_select_failed", "conversation_verify_failed", "target_not_visible", "verify_mismatch"}:
            suggestions.append("先刷新上下文列表，并确认目标对象已处于可见状态。")
        if reason in {"input_box_interface_missing", "input_box_interface_unavailable"}:
            suggestions.append("切回标准输入界面，确保输入框可见后再试。")
        if reason == "empty_draft_text":
            suggestions.append("先生成或补全回复草稿，再执行发送。")
        if result.get("risk_guard", {}).get("risk_level") == "medium":
            suggestions.append("人工复核金额、时间、承诺措辞和发送对象。")

    if operation == "select_conversation" and reason:
        suggestions.append("先让目标对象进入可见区域，再重新切换。")

    if not suggestions and not result.get("ok"):
        suggestions.append("检查当前应用是否在前台且处于标准输入界面后重试。")

    return suggestions
