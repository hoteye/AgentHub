from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cli.agent_cli.models import ReferenceContextItem, RolloutItem, ThreadHistoryTurn
from cli.agent_cli.startup_debug import startup_profile_log, startup_timer

if TYPE_CHECKING:
    from cli.agent_cli.thread_store import ThreadStore


def resume_thread_from_path(store: ThreadStore, rollout_path: str | Path) -> dict[str, Any]:
    resolved_path = store._resolve_existing_rollout_path(rollout_path)
    record = store._ensure_thread_record_for_rollout_path(resolved_path)
    payload = resume_thread(store, str(record.get("thread_id") or ""))
    payload["resume_source"] = "path"
    payload["resume_path"] = str(resolved_path)
    return payload


def resume_thread_from_history(
    store: ThreadStore,
    history: list[dict[str, Any]],
    *,
    name: str | None = None,
    cwd: str | None = None,
    provider_status: dict[str, Any] | None = None,
    runtime_policy_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_items = store._rollout_seed_items_from_history(history)
    thread_name = str(name or "").strip() or store._name_from_history(history) or None
    record = store.start_thread(
        name=thread_name,
        cwd=cwd,
        provider_status=provider_status,
        runtime_policy_status=runtime_policy_status,
    )
    if seed_items:
        store.append_rollout_items(record.thread_id, seed_items)
    payload = resume_thread(store, record.thread_id)
    payload["resume_source"] = "history"
    return payload


def resume_thread(store: ThreadStore, thread_id: str) -> dict[str, Any]:
    with startup_timer("thread_store.resume.get_thread"):
        record = store.get_thread(thread_id)
        if record is None:
            raise ValueError(f"unknown thread: {thread_id}")
    with startup_timer("thread_store.resume.resolve_rollout_path"):
        rollout_path = store._resolve_rollout_path(thread_id, record)
    history: list[dict[str, str]] = []
    turns: list[ThreadHistoryTurn] = []
    rollout_items: list[dict[str, Any]] = []
    context_items: list[ReferenceContextItem] = []
    state: dict[str, Any] = {}
    base_history: list[dict[str, str]] = []
    legacy_history: list[dict[str, str]] = []
    base_context_items: list[ReferenceContextItem] = []
    base_state: dict[str, Any] = {}
    scoped_context_history: list[dict[str, str]] = []
    scoped_environment_history: list[dict[str, str]] = []
    scoped_context_items: list[ReferenceContextItem] = []
    scoped_state: dict[str, Any] = {}
    compacted_active = False
    if rollout_path.exists():
        with startup_timer("thread_store.resume.read_rollout"):
            raw_count = 0
            with rollout_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    raw_count += 1
                    payload = json.loads(line)
                    rollout_item = RolloutItem.from_dict(payload)
                    rollout_items.append(rollout_item.to_dict())
                    if rollout_item.item_type == "turn" and rollout_item.turn is not None:
                        turns.append(rollout_item.turn)
                        prefix_history = base_history if compacted_active else []
                        history = [*prefix_history, *store._history_from_turns(turns)]
                        context_items = store._dedupe_reference_context_items(
                            [*base_context_items, *store._context_items_from_turns(turns)]
                        )
                        state = store._state_from_turns(turns) or dict(base_state)
                        continue
                    if rollout_item.item_type == "response_item":
                        scope = str(rollout_item.payload.get("scope") or "").strip()
                        if scope == "turn_context":
                            history_item = store._history_item_from_rollout_payload(
                                rollout_item.payload
                            )
                            if history_item is None:
                                continue
                            source_name = str(rollout_item.payload.get("source") or "").strip()
                            if source_name == "environment_context":
                                scoped_environment_history.append(history_item)
                            else:
                                scoped_context_history.append(history_item)
                            continue
                        history_item = store._history_item_from_rollout_payload(
                            rollout_item.payload
                        )
                        if history_item is not None:
                            if compacted_active:
                                base_history.append(history_item)
                                history = [*base_history, *store._history_from_turns(turns)]
                            else:
                                legacy_history.append(history_item)
                                history = list(legacy_history)
                        continue
                    if rollout_item.item_type == "turn_context":
                        turn_context = rollout_item.turn_context
                        if turn_context is None:
                            continue
                        for input_item in list(turn_context.items or []):
                            history_item = store._history_item_from_planner_input_item(
                                input_item.item.to_dict()
                            )
                            if history_item is None:
                                continue
                            if input_item.source == "environment_context":
                                scoped_environment_history.append(history_item)
                            else:
                                scoped_context_history.append(history_item)
                        for context_item in list(turn_context.reference_context_items or []):
                            if str(context_item.item_type or "").strip():
                                scoped_context_items.append(context_item)
                        scoped_state = dict(turn_context.state or {})
                        continue
                    if rollout_item.item_type == "reference_context_item":
                        scope = str(rollout_item.payload.get("scope") or "").strip()
                        context_item_source = store._reference_context_item_from_rollout_payload(
                            rollout_item.payload
                        )
                        if context_item_source is None:
                            continue
                        if scope == "turn_context":
                            scoped_context_items.append(context_item_source)
                            continue
                        base_context_items.append(context_item_source)
                        context_items = store._dedupe_reference_context_items(
                            [*base_context_items, *store._context_items_from_turns(turns)]
                        )
                        continue
                    if rollout_item.item_type == "state_snapshot":
                        scope = str(rollout_item.payload.get("scope") or "").strip()
                        snapshot = store._state_snapshot_from_rollout_payload(rollout_item.payload)
                        if scope == "turn_context":
                            scoped_state = snapshot
                            continue
                        base_state = snapshot
                        state = store._state_from_turns(turns) or dict(base_state)
                        continue
                    if rollout_item.item_type == "thread_rolled_back":
                        turns = store._drop_last_n_user_turns(
                            turns,
                            store._rollback_turn_count(rollout_item.payload),
                        )
                        prefix_history = base_history if compacted_active else []
                        history = [*prefix_history, *store._history_from_turns(turns)]
                        context_items = store._dedupe_reference_context_items(
                            [*base_context_items, *store._context_items_from_turns(turns)]
                        )
                        state = store._state_from_turns(turns) or dict(base_state)
                        continue
                    if rollout_item.item_type == "compacted":
                        compacted_active = True
                        base_history = store._compacted_replacement_history(
                            rollout_item.payload,
                            existing_history=history,
                        )
                        history = list(base_history)
                        turns = []
                        base_context_items = []
                        context_items = []
                        base_state = {}
                        state = {}
            startup_profile_log(
                "profile.thread_store.resume.rollout "
                f"path={rollout_path} lines={raw_count} items={len(rollout_items)} "
                f"turns={len(turns)}"
            )
    with startup_timer("thread_store.resume.context_state"):
        deduped_context_items = store._dedupe_reference_context_items(
            [ReferenceContextItem.from_dict(item.to_dict()) for item in context_items]
        )
        effective_state = dict(state)
        if scoped_environment_history and not list(
            effective_state.get("environment_context_history") or []
        ):
            effective_state["environment_context_history"] = list(scoped_environment_history[-16:])
        if scoped_context_history and not list(effective_state.get("context_update_history") or []):
            effective_state["context_update_history"] = list(scoped_context_history[-16:])
        if scoped_state:
            if "environment_context_snapshot" not in effective_state and isinstance(
                scoped_state.get("environment_context_snapshot"), dict
            ):
                effective_state["environment_context_snapshot"] = dict(
                    scoped_state.get("environment_context_snapshot") or {}
                )
            if "workspace_context_snapshot" not in effective_state and isinstance(
                scoped_state.get("workspace_context_snapshot"), dict
            ):
                effective_state["workspace_context_snapshot"] = dict(
                    scoped_state.get("workspace_context_snapshot") or {}
                )
        if "workspace_context_snapshot" not in effective_state:
            latest_workspace_item = None
            for item in list(scoped_context_items)[::-1]:
                if str(item.item_type or "").strip() == "workspace_context":
                    latest_workspace_item = item
                    break
            if latest_workspace_item is not None:
                metadata = dict(latest_workspace_item.metadata or {})
                effective_state["workspace_context_snapshot"] = {
                    "cwd": str(latest_workspace_item.path or record.get("cwd") or ""),
                    "trust_level": str(metadata.get("trust_level") or ""),
                    "instructions_text": str(metadata.get("instructions_excerpt") or ""),
                    "instructions_digest": str(metadata.get("instructions_digest") or ""),
                    "instructions_truncated": False,
                    "docs": [
                        entry
                        for entry in list(metadata.get("docs") or [])
                        if isinstance(entry, dict)
                    ],
                    "skills": [
                        entry
                        for entry in list(metadata.get("skills") or [])
                        if isinstance(entry, dict)
                    ],
                }
    with startup_timer("thread_store.resume.set_active_thread"):
        with store._lock, store._connection() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('active_thread_id', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (thread_id,),
            )
            conn.commit()
    planner_fallback_history = list(
        base_history if compacted_active else ([] if turns else legacy_history)
    )
    with startup_timer("thread_store.resume.planner_history"):
        planner_history = store._planner_history_from_turns(
            turns,
            fallback_history=planner_fallback_history,
        )
    with startup_timer("thread_store.resume.planner_input_items"):
        planner_input_items = store._planner_input_items_from_rollout_items(
            rollout_items,
            fallback_history=planner_fallback_history,
        )
    with startup_timer("thread_store.resume.serialize_payload"):
        return {
            "thread": record,
            "history": history,
            "base_history": base_history,
            "planner_history": planner_history,
            "planner_input_items": planner_input_items,
            "turns": [turn.to_dict() for turn in turns],
            "rollout_items": rollout_items,
            "context_items": [item.to_dict() for item in deduped_context_items],
            "state": effective_state,
            "resume_source": "thread_id",
        }
