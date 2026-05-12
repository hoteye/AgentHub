from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


RESEARCH_HINTS: Tuple[str, ...] = (
    "research",
    "look up",
    "lookup",
    "search",
    "find",
    "inspect",
    "investigate",
    "read",
    "scan",
    "gather",
    "docs",
    "documentation",
    "reference",
    "调研",
    "检索",
    "搜索",
    "查找",
    "查证",
    "看看",
    "阅读",
    "收集",
)

VERIFY_HINTS: Tuple[str, ...] = (
    "verify",
    "validation",
    "validate",
    "check",
    "confirm",
    "compare",
    "cross-check",
    "review",
    "audit",
    "smoke",
    "验证",
    "核对",
    "确认",
    "检查",
    "复核",
    "比对",
    "复现",
)

LONG_RUNNING_HINTS: Tuple[str, ...] = (
    "benchmark",
    "bench",
    "latency",
    "performance",
    "perf",
    "load test",
    "stress test",
    "e2e",
    "full test",
    "test suite",
    "integration test",
    "compile",
    "build",
    "install",
    "benchmarking",
    "基准",
    "压测",
    "跑测试",
    "全量测试",
    "编译",
    "构建",
    "安装",
    "耗时",
)

WORKSPACE_MUTATING_HINTS: Tuple[str, ...] = (
    "edit",
    "modify",
    "write",
    "patch",
    "update",
    "create",
    "implement",
    "refactor",
    "rename",
    "delete",
    "move",
    "修改",
    "编辑",
    "实现",
    "重构",
    "写入",
    "新增",
    "删除",
    "改代码",
    "补丁",
)

CONTEXT_SENSITIVE_HINTS: Tuple[str, ...] = (
    "current context",
    "current thread",
    "conversation history",
    "above context",
    "follow up",
    "continue current task",
    "parent context",
    "当前上下文",
    "当前线程",
    "当前对话",
    "继续当前任务",
    "接着刚才",
)


def normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def contains_any(text: str, hints: Tuple[str, ...]) -> bool:
    return any(str(hint).strip().lower() in text for hint in hints if str(hint).strip())


def spawn_task_text(arguments: Dict[str, Any] | None) -> str:
    payload = dict(arguments or {})
    return normalized_text(payload.get("task") or payload.get("message") or payload.get("prompt"))


def infer_task_shape(task_text: str) -> str:
    if contains_any(task_text, WORKSPACE_MUTATING_HINTS):
        return "workspace_mutating"
    if contains_any(task_text, CONTEXT_SENSITIVE_HINTS):
        return "context_sensitive"
    if contains_any(task_text, LONG_RUNNING_HINTS):
        return "long_running"
    return "read_only"


def infer_task_reason(task_text: str, inferred_shape: str) -> str:
    if contains_any(task_text, VERIFY_HINTS):
        return "verify_side_task"
    if inferred_shape == "long_running":
        return "long_running_exec"
    if contains_any(task_text, RESEARCH_HINTS) or inferred_shape == "read_only":
        return "research_side_task"
    return "background_side_task"


def planner_defaulted_fields(
    raw_arguments: Dict[str, Any],
    enriched_arguments: Dict[str, Any],
    *,
    field_names: Tuple[str, ...],
    argument_is_supplied_fn: Callable[[Dict[str, Any], str], bool],
) -> list[str]:
    defaulted: list[str] = []
    for field_name in field_names:
        if field_name not in enriched_arguments:
            continue
        if not argument_is_supplied_fn(raw_arguments, field_name):
            defaulted.append(field_name)
    return defaulted


def planner_policy_basis(
    tool_name: str,
    raw_arguments: Dict[str, Any],
    enriched_arguments: Dict[str, Any],
    *,
    defaulted_fields: list[str],
    normalize_spawn_agent_role_fn: Callable[[Any], str],
    spawn_task_text_fn: Callable[[Dict[str, Any] | None], str],
    argument_is_supplied_fn: Callable[[Dict[str, Any], str], bool],
) -> str:
    normalized_name = str(tool_name or "").strip()
    if normalized_name == "spawn_agent":
        if not defaulted_fields:
            return "explicit_arguments"
        basis: list[str] = []
        normalized_role = normalize_spawn_agent_role_fn(
            raw_arguments.get("role") or raw_arguments.get("agent_type")
        )
        task_text = spawn_task_text_fn(raw_arguments)
        if (
            "async" in defaulted_fields
            and normalized_role == "teammate"
            and not argument_is_supplied_fn(raw_arguments, "mode")
        ):
            basis.append("teammate_role_default")
        if any(field in defaulted_fields for field in ("reason", "task_shape")) and task_text:
            basis.append("task_text_inference")
        if any(field in defaulted_fields for field in ("mode", "wait_required")):
            basis.append("delegation_policy_defaults")
        if not basis:
            basis.append("delegation_policy_defaults")
        return "+".join(basis)
    if normalized_name == "wait_agent":
        if not defaulted_fields:
            return "explicit_arguments"
        basis: list[str] = []
        if "reason" in defaulted_fields:
            basis.append("wait_reason_default")
        if "wait_required" in defaulted_fields:
            basis.append("blocking_join_default")
        return "+".join(basis or ["delegation_policy_defaults"])
    if normalized_name == "agent_workflow":
        return "explicit_arguments"
    if normalized_name == "recover_agent":
        if "action" in defaulted_fields:
            return "retry_step_default"
        return "explicit_arguments"
    return "explicit_arguments"
