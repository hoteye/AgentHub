from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import RunKind, RunRecord, RunStatus, utc_now_iso


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(
        self,
        *,
        run_id: str,
        kind: RunKind | str,
        thread_id: str = "",
        parent_run_id: str = "",
        summary: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RunRecord:
        if not str(run_id or "").strip():
            raise ValueError("run_id is required")
        if run_id in self._runs:
            raise ValueError(f"run already exists: {run_id}")
        record = RunRecord(
            run_id=run_id,
            kind=self._coerce_kind(kind),
            status=RunStatus.CREATED,
            thread_id=str(thread_id or ""),
            parent_run_id=str(parent_run_id or ""),
            summary=str(summary or ""),
            payload=dict(payload or {}),
        )
        self._runs[run_id] = record
        return replace(record)

    def update(
        self,
        run_id: str,
        *,
        status: RunStatus | str | None = None,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunRecord:
        record = self._require(run_id)
        now = utc_now_iso()
        next_status = self._coerce_status(status) if status is not None else record.status
        next_summary = record.summary if summary is None else str(summary)
        next_payload = dict(record.payload or {})
        if payload:
            next_payload.update(dict(payload))
        next_record = replace(
            record,
            status=next_status,
            summary=next_summary,
            payload=next_payload,
            updated_at=now,
        )
        if next_status is RunStatus.RUNNING and not record.started_at:
            next_record = replace(next_record, started_at=now)
        if next_status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.TIMED_OUT}:
            next_record = replace(
                next_record,
                finished_at=record.finished_at or now,
                timed_out_at=(record.timed_out_at or now) if next_status is RunStatus.TIMED_OUT else record.timed_out_at,
            )
        if next_status is RunStatus.CANCELLED:
            next_record = replace(
                next_record,
                cancelled_at=record.cancelled_at or now,
                finished_at=record.finished_at or now,
            )
        self._runs[run_id] = next_record
        return replace(next_record)

    def cancel(self, run_id: str, *, summary: str | None = None) -> RunRecord:
        default_summary = "cancelled" if summary is None else summary
        return self.update(run_id, status=RunStatus.CANCELLED, summary=default_summary)

    def timeout(self, run_id: str, *, summary: str | None = None) -> RunRecord:
        default_summary = "timed out" if summary is None else summary
        return self.update(run_id, status=RunStatus.TIMED_OUT, summary=default_summary)

    def finish(
        self,
        run_id: str,
        *,
        failed: bool = False,
        timed_out: bool = False,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunRecord:
        if timed_out:
            status = RunStatus.TIMED_OUT
            default_summary = "timed out" if summary is None else summary
        else:
            status = RunStatus.FAILED if failed else RunStatus.COMPLETED
            default_summary = ("failed" if failed else "completed") if summary is None else summary
        return self.update(run_id, status=status, summary=default_summary, payload=payload)

    def get(self, run_id: str) -> RunRecord | None:
        record = self._runs.get(run_id)
        return replace(record) if record is not None else None

    def list(
        self,
        *,
        run_id: str | None = None,
        thread_id: str | None = None,
        parent_run_id: str | None = None,
        status: RunStatus | str | None = None,
    ) -> list[RunRecord]:
        status_filter = self._coerce_status(status) if status is not None else None
        items = []
        for record in self._runs.values():
            if run_id is not None and record.run_id != str(run_id):
                continue
            if thread_id is not None and record.thread_id != str(thread_id):
                continue
            if parent_run_id is not None and record.parent_run_id != str(parent_run_id):
                continue
            if status_filter is not None and record.status is not status_filter:
                continue
            items.append(replace(record))
        return sorted(items, key=lambda item: (item.created_at, item.run_id))

    @staticmethod
    def _coerce_kind(kind: RunKind | str) -> RunKind:
        if isinstance(kind, RunKind):
            return kind
        try:
            return RunKind(str(kind or "").strip().lower())
        except ValueError:
            return RunKind.CUSTOM

    @staticmethod
    def _coerce_status(status: RunStatus | str) -> RunStatus:
        if isinstance(status, RunStatus):
            return status
        return RunStatus(str(status or "").strip().lower())

    def _require(self, run_id: str) -> RunRecord:
        record = self._runs.get(run_id)
        if record is None:
            raise KeyError(f"unknown run_id: {run_id}")
        return record
