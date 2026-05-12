from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.models import ReferenceContextItem
from cli.agent_cli.provider import request_prelude_contract
from cli.agent_cli.runtime_services import planner_context_runtime


class _RuntimeStub:
    def __init__(self) -> None:
        self.runtime_policy = SimpleNamespace(
            sandbox_mode="workspace-write",
            approval_policy="never",
        )
        self.cwd = "/tmp/work"

    @staticmethod
    def web_access_allowed() -> bool:
        return True

    @staticmethod
    def _planner_environment_context_items(*, snapshot_override=None):
        del snapshot_override
        return []

    @staticmethod
    def _planner_workspace_context_items(*, snapshot_override=None):
        del snapshot_override
        return []

    @staticmethod
    def _normalized_history_item(item):
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "developer", "user", "assistant"} or not content:
            return None
        return {"role": role, "content": content}


def test_planner_prelude_keeps_workspace_baseline_when_memory_items_exist() -> None:
    runtime = _RuntimeStub()
    memory_item = ReferenceContextItem(
        item_type="memory",
        source="runtime:memory_store",
        label="project_memory",
        path="memory://mem_1",
        description="recalled by relevance",
        metadata={"memory_id": "mem_1"},
    )
    workspace_snapshot = {
        "cwd": "/tmp/work",
        "trust_level": "trusted",
        "instructions_text": "workspace instructions",
        "instructions_digest": "digest-workspace",
        "docs": [{"path": "/tmp/work/AENGTHUB.md", "size": 12, "mtime_ns": 1}],
        "skills": [],
    }
    prelude_items = planner_context_runtime.planner_context_input_items(
        runtime,
        environment_snapshot={},
        workspace_snapshot=workspace_snapshot,
        pending_context_items=[memory_item],
        workspace_baseline_missing=True,
    )
    reference_items = [item for item in prelude_items if str(item.get("type") or "") == "reference_context_item"]
    assert len(reference_items) == 2
    reference_item_types = {
        str((item.get("item") or {}).get("item_type") or "")
        for item in reference_items
        if isinstance(item, dict)
    }
    assert "memory" in reference_item_types
    assert "workspace_context" in reference_item_types
    contract = request_prelude_contract(prelude_items)
    assert "workspace_context" in list(contract.get("section_order") or [])
