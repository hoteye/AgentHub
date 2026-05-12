from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from cli.agent_cli.runtime_paths import project_local_data_dir

from .taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    OrchestrationEvent,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)


_NON_ALNUM = re.compile(r"[^A-Za-z0-9._-]+")


def orchestration_root_dir(*, root: Path | None = None) -> Path:
    return project_local_data_dir(root=root) / "orchestration"


def _slug(text: str, *, default: str) -> str:
    normalized = _NON_ALNUM.sub("_", str(text or "").strip()).strip("._-")
    return normalized or default


def orchestration_root_dir(*, root: Path | None = None) -> Path:
    return project_local_data_dir(root=root) / "orchestration"


def _read_json(path: Path) -> Dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)


@dataclass(slots=True)
class TaskbookStorage:
    base_dir: Path

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls, *, root: Path | None = None) -> "TaskbookStorage":
        return cls(orchestration_root_dir(root=root))

    @property
    def root_dir(self) -> Path:
        return self.base_dir

    def ensure_run_layout(self, run_id: str) -> Path:
        run_dir = self.run_dir(run_id)
        (run_dir / "taskbooks").mkdir(parents=True, exist_ok=True)
        (run_dir / "cards").mkdir(parents=True, exist_ok=True)
        (run_dir / "events").mkdir(parents=True, exist_ok=True)
        (run_dir / "projections" / "cards").mkdir(parents=True, exist_ok=True)
        return run_dir

    def list_run_ids(self) -> List[str]:
        run_ids: List[str] = []
        for child in sorted(self.base_dir.iterdir()) if self.base_dir.exists() else []:
            if child.is_dir() and (child / "run.json").exists():
                run_ids.append(child.name)
        return run_ids

    def run_dir(self, run_id: str) -> Path:
        return self.base_dir / str(run_id or "").strip()

    def run_file_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def taskbooks_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "taskbooks"

    def taskbook_file_path(self, run_id: str, version: int) -> Path:
        return self.taskbooks_dir(run_id) / f"taskbook_v{int(version):03d}.json"

    def cards_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "cards"

    def card_dir(self, run_id: str, card_id: str) -> Path:
        return self.cards_dir(run_id) / str(card_id or "").strip()

    def card_spec_path(self, run_id: str, card_id: str) -> Path:
        return self.card_dir(run_id, card_id) / "spec.json"

    def card_state_path(self, run_id: str, card_id: str) -> Path:
        return self.card_dir(run_id, card_id) / "state.json"

    def card_results_dir(self, run_id: str, card_id: str) -> Path:
        return self.card_dir(run_id, card_id) / "results"

    def card_acceptance_dir(self, run_id: str, card_id: str) -> Path:
        return self.card_dir(run_id, card_id) / "acceptance"

    def card_result_path(self, run_id: str, card_id: str, result_id: str) -> Path:
        slug = _slug(result_id, default="result")
        return self.card_results_dir(run_id, card_id) / f"{slug}.json"

    def card_acceptance_path(self, run_id: str, card_id: str, acceptance_id: str) -> Path:
        slug = _slug(acceptance_id, default="acceptance")
        return self.card_acceptance_dir(run_id, card_id) / f"{slug}.json"

    def events_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events"

    def event_file_path(self, run_id: str, seq: int, event_type: str) -> Path:
        slug = _slug(event_type, default="event")
        return self.events_dir(run_id) / f"{int(seq):06d}_{slug}.json"

    def write_run(self, run: ComplexTaskRun) -> Path:
        self.ensure_run_layout(run.run_id)
        path = self.run_file_path(run.run_id)
        _write_json_atomic(path, run.to_dict())
        return path

    def save_run(self, run: ComplexTaskRun) -> Path:
        return self.write_run(run)

    def read_run(self, run_id: str) -> ComplexTaskRun | None:
        path = self.run_file_path(run_id)
        if not path.exists():
            return None
        return ComplexTaskRun.from_dict(_read_json(path))

    def append_taskbook(self, taskbook: TaskbookSnapshot) -> Path:
        self.ensure_run_layout(taskbook.run_id)
        path = self.taskbook_file_path(taskbook.run_id, taskbook.version)
        _write_json_atomic(path, taskbook.to_dict())
        return path

    def save_taskbook(self, taskbook: TaskbookSnapshot) -> Path:
        return self.append_taskbook(taskbook)

    def read_taskbook(self, run_id: str, version: int) -> TaskbookSnapshot | None:
        path = self.taskbook_file_path(run_id, version)
        if not path.exists():
            return None
        return TaskbookSnapshot.from_dict(_read_json(path))

    def list_taskbooks(self, run_id: str) -> List[TaskbookSnapshot]:
        items: List[TaskbookSnapshot] = []
        for path in sorted(self.taskbooks_dir(run_id).glob("taskbook_v*.json")):
            items.append(TaskbookSnapshot.from_dict(_read_json(path)))
        return items

    def latest_taskbook(self, run_id: str) -> TaskbookSnapshot | None:
        taskbooks = self.list_taskbooks(run_id)
        if not taskbooks:
            return None
        return max(taskbooks, key=lambda item: item.version)

    def write_card_spec(self, run_id: str, card: TaskCard) -> Path:
        self.ensure_run_layout(run_id)
        path = self.card_spec_path(run_id, card.card_id)
        _write_json_atomic(path, card.to_dict())
        return path

    def save_card_spec(self, run_id: str, card: TaskCard) -> Path:
        return self.write_card_spec(run_id, card)

    def read_card_spec(self, run_id: str, card_id: str) -> TaskCard | None:
        path = self.card_spec_path(run_id, card_id)
        if not path.exists():
            return None
        return TaskCard.from_dict(_read_json(path))

    def write_card_state(self, run_id: str, state: TaskCardState) -> Path:
        self.ensure_run_layout(run_id)
        path = self.card_state_path(run_id, state.card_id)
        _write_json_atomic(path, state.to_dict())
        return path

    def save_card_state(self, run_id: str, state: TaskCardState) -> Path:
        return self.write_card_state(run_id, state)

    def read_card_state(self, run_id: str, card_id: str) -> TaskCardState | None:
        path = self.card_state_path(run_id, card_id)
        if not path.exists():
            return None
        return TaskCardState.from_dict(_read_json(path))

    def list_card_ids(self, run_id: str) -> List[str]:
        items: List[str] = []
        for path in sorted(self.cards_dir(run_id).iterdir()) if self.cards_dir(run_id).exists() else []:
            if path.is_dir():
                items.append(path.name)
        return items

    def list_card_specs(self, run_id: str) -> List[TaskCard]:
        items: List[TaskCard] = []
        for card_id in self.list_card_ids(run_id):
            card = self.read_card_spec(run_id, card_id)
            if card is not None:
                items.append(card)
        return items

    def list_card_states(self, run_id: str) -> List[TaskCardState]:
        items: List[TaskCardState] = []
        for card_id in self.list_card_ids(run_id):
            state = self.read_card_state(run_id, card_id)
            if state is not None:
                items.append(state)
        return items

    def append_card_result(self, run_id: str | CardResult, result: CardResult | None = None) -> Path:
        item = run_id if isinstance(run_id, CardResult) else result
        if not isinstance(item, CardResult):
            raise TypeError("append_card_result requires a CardResult")
        if isinstance(run_id, str) and not item.run_id:
            item.run_id = run_id
        self.ensure_run_layout(item.run_id)
        path = self.card_result_path(item.run_id, item.card_id, item.result_id)
        _write_json_atomic(path, item.to_dict())
        return path

    def list_card_results(self, run_id: str, card_id: str) -> List[CardResult]:
        rows: List[tuple[tuple[str, int, str], CardResult]] = []
        for path in sorted(self.card_results_dir(run_id, card_id).glob("*.json")):
            item = CardResult.from_dict(_read_json(path))
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            rows.append(((str(item.reported_at or ""), int(mtime_ns), path.name), item))
        rows.sort(key=lambda row: row[0])
        return [item for _, item in rows]

    def latest_card_result(self, run_id: str, card_id: str) -> CardResult | None:
        results = self.list_card_results(run_id, card_id)
        if not results:
            return None
        return results[-1]

    def append_card_acceptance(self, run_id: str | CardAcceptance, acceptance: CardAcceptance | None = None) -> Path:
        item = run_id if isinstance(run_id, CardAcceptance) else acceptance
        if not isinstance(item, CardAcceptance):
            raise TypeError("append_card_acceptance requires a CardAcceptance")
        if isinstance(run_id, str) and not item.run_id:
            item.run_id = run_id
        self.ensure_run_layout(item.run_id)
        path = self.card_acceptance_path(item.run_id, item.card_id, item.acceptance_id)
        _write_json_atomic(path, item.to_dict())
        return path

    def list_card_acceptance(self, run_id: str, card_id: str) -> List[CardAcceptance]:
        rows: List[tuple[tuple[str, int, str], CardAcceptance]] = []
        for path in sorted(self.card_acceptance_dir(run_id, card_id).glob("*.json")):
            item = CardAcceptance.from_dict(_read_json(path))
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                mtime_ns = 0
            rows.append(((str(item.reviewed_at or ""), int(mtime_ns), path.name), item))
        rows.sort(key=lambda row: row[0])
        return [item for _, item in rows]

    def latest_card_acceptance(self, run_id: str, card_id: str) -> CardAcceptance | None:
        items = self.list_card_acceptance(run_id, card_id)
        if not items:
            return None
        return items[-1]

    def append_event(self, run_id: str | OrchestrationEvent, event: OrchestrationEvent | None = None) -> Path:
        item = run_id if isinstance(run_id, OrchestrationEvent) else event
        if not isinstance(item, OrchestrationEvent):
            raise TypeError("append_event requires an OrchestrationEvent")
        if isinstance(run_id, str) and not item.run_id:
            item.run_id = run_id
        self.ensure_run_layout(item.run_id)
        path = self.event_file_path(item.run_id, item.seq, item.event_type)
        _write_json_atomic(path, item.to_dict())
        return path

    def list_events(self, run_id: str) -> List[OrchestrationEvent]:
        items: List[OrchestrationEvent] = []
        for path in sorted(self.events_dir(run_id).glob("*.json")):
            items.append(OrchestrationEvent.from_dict(_read_json(path)))
        return items

    def load_run_bundle(self, run_id: str) -> Dict[str, object]:
        card_results = {card_id: self.list_card_results(run_id, card_id) for card_id in self.list_card_ids(run_id)}
        card_acceptance = {
            card_id: self.list_card_acceptance(run_id, card_id)
            for card_id in self.list_card_ids(run_id)
        }
        return {
            "run": self.read_run(run_id),
            "taskbooks": self.list_taskbooks(run_id),
            "card_specs": {card.card_id: card for card in self.list_card_specs(run_id)},
            "card_states": {state.card_id: state for state in self.list_card_states(run_id)},
            "card_results": {card_id: items for card_id, items in card_results.items() if items},
            "card_acceptance": {card_id: items for card_id, items in card_acceptance.items() if items},
            "events": self.list_events(run_id),
        }

    def projection_taskbook_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "projections" / "taskbook.md"

    def projection_card_path(self, run_id: str, card_id: str) -> Path:
        return self.run_dir(run_id) / "projections" / "cards" / f"{str(card_id or '').strip()}.md"

    def write_projection(self, run_id: str, *, content: str, card_id: str = "") -> Path:
        self.ensure_run_layout(run_id)
        path = self.projection_card_path(run_id, card_id) if card_id else self.projection_taskbook_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content or ""), encoding="utf-8")
        return path
