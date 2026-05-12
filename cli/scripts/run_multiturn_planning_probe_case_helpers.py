from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationCommand:
    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class SeedFile:
    path: str
    content: str


@dataclass(frozen=True)
class CaseSpec:
    name: str
    description: str
    prompts: tuple[str, ...]
    min_plan_turns: int = 0
    require_replan: bool = False
    expect_no_plan: bool = False
    expected_files: tuple[str, ...] = ()
    forbidden_files: tuple[str, ...] = ()
    validation_commands: tuple[ValidationCommand, ...] = ()
    seed_files: tuple[SeedFile, ...] = ()


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        name="case_a_linear_build",
        description="线性多轮构建，验证复杂任务会建 plan，并在每轮收口 todo_list。",
        prompts=(
            (
                "当前目录是空的。请创建一个最小 Python CLI `note_stats.py`：\n"
                "- 读取 UTF-8 文本文件，每行格式 `title,tag,words`\n"
                "- 统计 total_notes、total_words、tag_count\n"
                "- 默认输出人类可读摘要\n"
                "- 写一个最小 README.md\n"
                "- 暂时不要写测试\n"
                "完成后告诉我你创建了哪些文件。"
            ),
            (
                "继续迭代：\n"
                "- 增加 `--json`\n"
                "- 忽略空行和以 `#` 开头的注释行\n"
                "- 坏行写到 stderr 并跳过\n"
                "- 增加 `sample_notes.txt`\n"
                "- 实际运行两次示例"
            ),
            (
                "最后补质量：\n"
                "- 增加 pytest 测试\n"
                "- 修复前两轮留下的问题\n"
                "- 自己运行测试\n"
                "最后只汇报：修改文件、测试是否通过。"
            ),
        ),
        min_plan_turns=2,
        require_replan=True,
        expected_files=("note_stats.py", "README.md", "sample_notes.txt"),
        validation_commands=(ValidationCommand(name="pytest", command=("pytest", "-q")),),
    ),
    CaseSpec(
        name="case_b_replan_after_failure",
        description="需求追加到已有实现，验证会在补测试/修遗留问题时重规划。",
        prompts=(
            (
                "当前目录是空的。请实现 `inventory_report.py`：\n"
                "- 读取 UTF-8 文本文件，每行格式 `name,qty,price`\n"
                "- 输出 total_items、total_quantity、total_value\n"
                "- 默认输出简洁摘要\n"
                "- 写一个最小 README.md\n"
                "- 先不要写测试"
            ),
            (
                "继续：\n"
                "- 增加 `--json`\n"
                "- 新增 `sample_inventory.txt`\n"
                "- 运行一次示例\n"
                "- 如果发现问题先修再继续"
            ),
            (
                "现在补测试，并且我要求：\n"
                "- price 支持小数\n"
                "- 非法 qty 或 price 要报到 stderr 并跳过\n"
                "- 自己运行 pytest\n"
                "最后只汇报修改文件和测试结果。"
            ),
        ),
        min_plan_turns=2,
        require_replan=True,
        expected_files=("inventory_report.py", "README.md", "sample_inventory.txt"),
        validation_commands=(ValidationCommand(name="pytest", command=("pytest", "-q")),),
    ),
    CaseSpec(
        name="case_c_scope_pivot",
        description="用户中途改需求，验证计划会切换到新目标而不是沿用旧路线。",
        prompts=(
            (
                "当前目录是空的。请做一个最小 CLI `text_clean.py`：\n"
                "- 输入文本文件\n"
                "- 去掉首尾空白\n"
                "- 合并连续空行\n"
                "- 输出到 stdout\n"
                "- 先不要写测试"
            ),
            (
                "我改需求了，不要继续做刚才那个。改成：\n"
                "- 处理 CSV\n"
                "- 删除空列\n"
                "- 输出为规范化 CSV\n"
                "- 文件名改为 `csv_clean.py`\n"
                "- README 也要同步改\n"
                "继续完成。"
            ),
            (
                "最后补测试并跑通。\n"
                "测试框架不限，但测试布局要保证在当前 workspace 根目录执行 `pytest -q` 可以收集并通过。\n"
                "最后只汇报：修改文件、测试是否通过。"
            ),
        ),
        min_plan_turns=2,
        require_replan=True,
        expected_files=("csv_clean.py", "README.md"),
        validation_commands=(ValidationCommand(name="pytest", command=("pytest", "-q")),),
    ),
    CaseSpec(
        name="case_d_no_plan_control",
        description="简单只读任务不应过度规划。",
        prompts=(
            "列出当前目录的一层文件和目录，不要修改任何文件。",
            "README.md 一共有几行？只回答结果，不要修改文件。",
        ),
        expect_no_plan=True,
        seed_files=(
            SeedFile(
                path="README.md",
                content="# Control Fixture\n\nThis is a tiny file.\n",
            ),
            SeedFile(path="notes.txt", content="alpha\nbeta\n"),
        ),
    ),
)


def _selected_cases(names: str) -> list[CaseSpec]:
    if not str(names or "").strip():
        return list(CASES)
    requested = {part.strip() for part in str(names).split(",") if part.strip()}
    selected = [case for case in CASES if case.name in requested]
    missing = sorted(requested - {case.name for case in selected})
    if missing:
        raise SystemExit(f"unknown cases: {', '.join(missing)}")
    return selected
