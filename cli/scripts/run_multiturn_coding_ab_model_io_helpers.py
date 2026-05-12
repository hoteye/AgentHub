from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseSpec:
    name: str
    prompts: tuple[str, ...]


DEFAULT_CASE = CaseSpec(
    name="task_stats_multiturn",
    prompts=(
        (
            "当前目录是空的。请创建一个最小 Python 命令行工具 `task_stats.py`：\n"
            "- 读取 UTF-8 文本文件，每行格式 `name,duration,status`\n"
            "- 统计 total_tasks、total_duration、success_count、failed_count\n"
            "- 默认输出简洁的人类可读摘要\n"
            "- 写一个最小 README.md 说明如何运行\n"
            "- 暂时不要写测试\n"
            "完成后告诉我你创建了哪些文件。"
        ),
        (
            "继续迭代刚才的工具：\n"
            "- 增加 `--json` 输出\n"
            "- 忽略空行和以 `#` 开头的注释行\n"
            "- 如果某行字段数不对或 duration 不是整数，要把 `line N: ...` 写到 stderr 并跳过\n"
            "- 新增一个示例输入文件 `sample_tasks.txt`\n"
            "完成后请实际运行两次示例：一次普通输出，一次 `--json` 输出。"
        ),
        (
            "最后补质量：\n"
            "- 增加 pytest 测试，至少覆盖正常统计、坏行跳过、`--json` 输出\n"
            "- 修复前两轮留下的问题\n"
            "- 自己运行测试\n"
            "最后只汇报：修改了哪些文件、测试是否通过。"
        ),
    ),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _inventory(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.exists():
        return items
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        items.append({"path": str(path.relative_to(root)), "size": path.stat().st_size})
    return items
