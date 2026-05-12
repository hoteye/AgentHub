from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.planner_postprocessing import (
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    sanitize_final_answer_text,
    structured_tool_fallback_text,
)

def test_canonical_file_tool_summary_lines_include_grounding() -> None:
    events = [
        ToolEvent(
            name="grep_files",
            ok=True,
            summary="paths=2",
            payload={
                "pattern": "provider status",
                "path": ".",
                "paths": ["cli/agent_cli/runtime_core/command_handlers.py", "cli/agent_cli/agent.py"],
            },
        ),
        ToolEvent(
            name="read_file",
            ok=True,
            summary="file loaded",
            payload={
                "file_path": "cli/agent_cli/runtime_core/command_handlers.py",
                "excerpt_lines": [{"line": 42, "text": "return _provider_status_text(runtime)"}],
            },
        ),
        ToolEvent(
            name="list_dir",
            ok=True,
            summary="entries=2",
            payload={
                "dir_path": "cli/agent_cli/runtime_core",
                "entries": [{"index": 1, "kind": "file", "path": "command_handlers.py"}],
            },
        ),
    ]

    lines = generic_tool_event_summary_lines(events)

    assert "top_path=cli/agent_cli/runtime_core/command_handlers.py" in lines[0]
    assert "excerpt=L42: return _provider_status_text(runtime)" in lines[1]
    assert "first_entry=[file] command_handlers.py" in lines[2]

def test_canonical_file_tool_context_blocks_preserve_paths_and_text() -> None:
    events = [
        ToolEvent(
            name="grep_files",
            ok=True,
            summary="paths=2",
            payload={
                "pattern": "provider status",
                "path": ".",
                "include": "*.py",
                "count": 2,
                "paths": ["cli/agent_cli/runtime_core/command_handlers.py", "cli/agent_cli/agent.py"],
                "text": "cli/agent_cli/runtime_core/command_handlers.py\ncli/agent_cli/agent.py",
            },
        ),
        ToolEvent(
            name="read_file",
            ok=True,
            summary="file loaded",
            payload={
                "file_path": "cli/agent_cli/runtime_core/command_handlers.py",
                "text": "L40: def handle_known_command(...)\nL41: ...",
                "line_count": 300,
                "returned_line_count": 2,
                "offset": 40,
                "limit": 20,
                "mode": "slice",
                "truncated": True,
                "excerpt_lines": [{"line": 40, "text": "def handle_known_command(...)"}, {"line": 41, "text": "..."}],
            },
        ),
        ToolEvent(
            name="list_dir",
            ok=True,
            summary="entries=2",
            payload={
                "dir_path": "cli/agent_cli/runtime_core",
                "offset": 1,
                "limit": 20,
                "depth": 2,
                "count": 2,
                "text": "E1: [file] command_handlers.py\nE2: [file] command_dispatch.py",
                "entries": [
                    {"index": 1, "kind": "file", "path": "command_handlers.py"},
                    {"index": 2, "kind": "file", "path": "command_dispatch.py"},
                ],
            },
        ),
    ]

    blocks = generic_tool_event_context_blocks(events)

    grep_block, read_block, list_block = blocks
    assert grep_block["paths"] == [
        "cli/agent_cli/runtime_core/command_handlers.py",
        "cli/agent_cli/agent.py",
    ]
    assert read_block["path"] == "cli/agent_cli/runtime_core/command_handlers.py"
    assert read_block["excerpt_lines"][0]["line"] == 40
    assert list_block["entries"][0]["path"] == "command_handlers.py"
    assert list_block["text"].startswith("E1: [file] command_handlers.py")

def test_sanitize_final_answer_text_flattens_markdown_heavy_summary_layout() -> None:
    value = """
## 一句话总结

这是总结。

---

### 1. CLI 主体能力

- Provider 路由
- Slash commands
""".strip()

    assert sanitize_final_answer_text(value) == (
        "一句话总结：\n\n"
        "这是总结。\n\n"
        "1. CLI 主体能力：\n\n"
        "- Provider 路由\n"
        "- Slash commands"
    )

def test_structured_tool_fallback_text_does_not_dump_exec_command_stdout() -> None:
    text = structured_tool_fallback_text(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={
                    "command": "pwd && rg -n \"assistant_text\" -S .",
                    "stdout": "very long raw output\n" * 200,
                    "function_call_output": "very long raw output\n" * 200,
                },
            )
        ]
    )

    assert text.startswith("工具已执行完成，但回答阶段未产出可展示内容。")
    assert "最后一个命令：" in text
    assert "very long raw output" not in text


def test_structured_tool_fallback_text_includes_short_exec_command_output() -> None:
    text = structured_tool_fallback_text(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command exited",
                payload={
                    "command": "sed -n '1,120p' helloworld.py",
                    "stdout": 'print("Hello, world!")\n',
                },
            )
        ]
    )

    assert "最后一个命令：`sed -n '1,120p' helloworld.py`" in text
    assert '工具输出：\nprint("Hello, world!")' in text
