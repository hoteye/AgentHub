from __future__ import annotations

import re

from cli.agent_cli.models import PromptAttachment, PromptResponse, ResponseInputItem
from cli.agent_cli.ui import transcript_controller_helpers, transcript_controller_runtime
from cli.agent_cli.ui.transcript_history import (
    TranscriptEntry,
    assistant_message_entry,
    commentary_message_entry,
    reasoning_message_entry,
    system_notice_entry,
    user_message_entry,
)


class TranscriptControllerMixin:
    _INVISIBLE_LINE_PREFIX_CHARS = ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060")
    _LIST_MARKER_ONLY_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-+*]|\d+[.)])\s*$")
    _HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")
    _RULE_LINE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
    _FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
    _LIST_LINE_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")

    @classmethod
    def _strip_invisible_line_prefix(cls, line: str) -> str:
        text = str(line or "")
        while text and text[0] in cls._INVISIBLE_LINE_PREFIX_CHARS:
            text = text[1:]
        return text

    @classmethod
    def _normalize_assistant_markdown_text(cls, content: str) -> str:
        source = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = source.split("\n")
        normalized: list[str] = []
        in_fence = False
        index = 0
        while index < len(lines):
            raw_line = lines[index]
            if re.match(r"^\s*(`{3,}|~{3,})", raw_line):
                in_fence = not in_fence
                normalized.append(raw_line)
                index += 1
                continue
            line = raw_line if in_fence else cls._strip_invisible_line_prefix(raw_line)
            if not in_fence:
                marker = cls._LIST_MARKER_ONLY_RE.match(line)
                if marker and index + 1 < len(lines):
                    next_line = cls._strip_invisible_line_prefix(lines[index + 1])
                    if next_line.strip() and not cls._LIST_MARKER_ONLY_RE.match(next_line):
                        normalized.append(
                            f"{marker.group('indent')}{marker.group('marker')} {next_line.lstrip()}"
                        )
                        index += 2
                        continue
            normalized.append(line)
            index += 1
        while normalized and not str(normalized[0]).strip():
            normalized.pop(0)
        while normalized and not str(normalized[-1]).strip():
            normalized.pop()
        return cls._flatten_markdown_heavy_assistant_text(normalized).strip()

    @classmethod
    def _flatten_markdown_heavy_assistant_text(cls, lines: list[str]) -> str:
        heading_count = sum(1 for line in lines if cls._HEADING_LINE_RE.match(line))
        rule_count = sum(1 for line in lines if cls._RULE_LINE_RE.match(line))
        if heading_count + rule_count <= 1:
            return "\n".join(cls._collapse_markdown_display_blank_lines(lines))

        flattened: list[str] = []
        in_fence = False
        for index, line in enumerate(lines):
            if cls._FENCE_LINE_RE.match(line):
                in_fence = not in_fence
                flattened.append(line)
                continue
            if in_fence:
                flattened.append(line)
                continue
            if cls._RULE_LINE_RE.match(line):
                if flattened and flattened[-1] != "":
                    flattened.append("")
                continue
            heading_match = cls._HEADING_LINE_RE.match(line)
            if heading_match:
                title = str(heading_match.group(1) or "").strip()
                if not title:
                    continue
                if flattened and flattened[-1] != "":
                    flattened.append("")
                flattened.append(cls._flatten_heading_text(title, lines=lines, index=index))
                flattened.append("")
                continue
            flattened.append(line)
        return "\n".join(cls._collapse_markdown_display_blank_lines(flattened))

    @classmethod
    def _flatten_heading_text(cls, title: str, *, lines: list[str], index: int) -> str:
        normalized = str(title or "").strip()
        if not normalized:
            return ""
        if normalized.endswith(("：", ":", "。", "！", "？", "!", "?")):
            return normalized
        for candidate in lines[index + 1 :]:
            stripped = str(candidate or "").strip()
            if not stripped:
                continue
            if cls._LIST_LINE_RE.match(stripped):
                return f"{normalized}："
            return f"{normalized}："
        return normalized

    @staticmethod
    def _collapse_markdown_display_blank_lines(lines: list[str]) -> list[str]:
        collapsed: list[str] = []
        last_blank = True
        for line in list(lines or []):
            text = str(line or "").rstrip()
            blank = not text.strip()
            if blank:
                if last_blank:
                    continue
                collapsed.append("")
                last_blank = True
                continue
            collapsed.append(text)
            last_blank = False
        while collapsed and not collapsed[0].strip():
            collapsed.pop(0)
        while collapsed and not collapsed[-1].strip():
            collapsed.pop()
        return collapsed

    def _restore_transcript_from_runtime_history(self) -> None:
        transcript_controller_helpers._restore_transcript_from_runtime_history(self)

    def _restore_transcript_turn(self, turn: dict[str, object]) -> None:
        transcript_controller_helpers._restore_transcript_turn(self, turn)

    def _render_response(self, response: PromptResponse) -> None:
        transcript_controller_helpers.render_response(self, response)

    def _write_request_user_input_summary(self, response: PromptResponse) -> None:
        transcript_controller_helpers._write_request_user_input_summary(self, response)

    def _request_user_input_transcript_text(self, key: str, **kwargs: object) -> str:
        return transcript_controller_helpers._request_user_input_transcript_text(
            self,
            key,
            **kwargs,
        )

    @staticmethod
    def _request_user_input_answer_values(value: object) -> list[str]:
        return transcript_controller_helpers._request_user_input_answer_values(value)

    def _apply_operator_transcript_projection(self, response: PromptResponse) -> None:
        transcript_controller_helpers._apply_operator_transcript_projection(self, response)

    def _project_operator_response_items(
        self,
        items: list[ResponseInputItem],
        *,
        projected_text: str,
    ) -> list[ResponseInputItem]:
        return transcript_controller_helpers._project_operator_response_items(
            items,
            projected_text=projected_text,
        )

    @staticmethod
    def _project_operator_turn_events(
        events: list[dict[str, object]],
        *,
        projected_text: str,
    ) -> list[dict[str, object]]:
        return transcript_controller_helpers._project_operator_turn_events(
            events,
            projected_text=projected_text,
        )

    def _operator_transcript_text(
        self,
        command_name: str,
        *,
        key_values: dict[str, str],
        assistant_text: str,
    ) -> str:
        return transcript_controller_helpers._operator_transcript_text(
            self,
            command_name,
            key_values=key_values,
            assistant_text=assistant_text,
        )

    def _operator_transcript_detail_lines(
        self,
        command_name: str,
        *,
        key_values: dict[str, str],
        assistant_text: str,
    ) -> list[str]:
        return transcript_controller_helpers._operator_transcript_detail_lines(
            self,
            command_name,
            key_values=key_values,
            assistant_text=assistant_text,
        )

    @staticmethod
    def _operator_pipe_segments(raw_line: str) -> list[str]:
        return transcript_controller_helpers._operator_pipe_segments(raw_line)

    @staticmethod
    def _operator_segment_map(segments: list[str]) -> tuple[list[str], dict[str, str]]:
        return transcript_controller_helpers._operator_segment_map(segments)

    def _operator_workflow_detail_lines(self, assistant_text: str) -> list[str]:
        return transcript_controller_helpers._operator_workflow_detail_lines(self, assistant_text)

    def _operator_background_task_detail_lines(self, assistant_text: str) -> list[str]:
        return transcript_controller_helpers._operator_background_task_detail_lines(
            self, assistant_text
        )

    def _single_operator_detail_line(self, command_name: str, key_values: dict[str, str]) -> str:
        return transcript_controller_helpers._single_operator_detail_line(
            self, command_name, key_values
        )

    def _render_canonical_turn_event_backfill(self, events: list[dict[str, object]]) -> None:
        transcript_controller_helpers._render_canonical_turn_event_backfill(self, events)

    def _write_system_notice(self, content: str) -> None:
        self._append_transcript_entry(system_notice_entry(content), leading_blank=True)

    def _write_user_prompt(
        self, content: str, *, attachments: list[PromptAttachment] | None = None
    ) -> None:
        self._append_transcript_entry(
            user_message_entry(content, attachments=attachments), leading_blank=True
        )

    def _localized_assistant_text(self, content: str) -> str:
        text = self._normalize_assistant_markdown_text(str(content or ""))
        if self._is_interrupt_terminal_message(text):
            return self._t("assistant.conversation_interrupted")
        return text

    def _assistant_message_status(self, content: str) -> str:
        text = self._normalize_assistant_markdown_text(str(content or ""))
        return "error" if self._is_interrupt_terminal_message(text) else "info"

    def _write_assistant_reply(self, content: str) -> None:
        self._append_transcript_entry(
            assistant_message_entry(
                self._localized_assistant_text(content),
                status=self._assistant_message_status(content),
            ),
            leading_blank=True,
        )

    def _write_commentary_reply(self, content: str) -> None:
        self._append_transcript_entry(
            commentary_message_entry(self._normalize_assistant_markdown_text(content)),
            leading_blank=True,
        )

    def _write_reasoning_reply(self, content: str) -> None:
        self._append_transcript_entry(reasoning_message_entry(content), leading_blank=True)

    def _scope_activity_key(self, activity_key: str | None) -> str | None:
        return transcript_controller_runtime.scope_activity_key(self, activity_key)

    def _scope_transcript_entry(self, entry: TranscriptEntry) -> TranscriptEntry:
        return transcript_controller_runtime.scope_transcript_entry(self, entry)

    def _append_transcript_lines(self, lines: list[str]) -> None:
        transcript_controller_runtime.append_transcript_lines(self, lines)

    def _append_transcript_entry(
        self, entry: TranscriptEntry, *, leading_blank: bool = False
    ) -> None:
        transcript_controller_runtime.append_transcript_entry(
            self, entry, leading_blank=leading_blank
        )

    def _append_transcript_entry_raw(
        self, entry: TranscriptEntry, *, leading_blank: bool = False
    ) -> None:
        transcript_controller_runtime.append_transcript_entry_raw(
            self, entry, leading_blank=leading_blank
        )

    def _replacement_index_for_entry(self, entry: TranscriptEntry) -> int | None:
        return transcript_controller_runtime.replacement_index_for_entry(self, entry)

    @staticmethod
    def _is_exploration_entry(entry: TranscriptEntry) -> bool:
        return transcript_controller_runtime.is_exploration_entry(entry)

    @staticmethod
    def _exploration_detail_items(entry: TranscriptEntry) -> list[tuple[str, str]]:
        return transcript_controller_runtime.exploration_detail_items(entry)

    @classmethod
    def _append_exploration_detail(
        cls,
        details: list[tuple[str, str]],
        detail: tuple[str, str],
    ) -> list[tuple[str, str]]:
        return transcript_controller_runtime.append_exploration_detail(details, detail)

    @classmethod
    def _build_exploration_entry(
        cls,
        base_entry: TranscriptEntry,
        *,
        details: list[tuple[str, str]],
        status: str,
    ) -> TranscriptEntry:
        return transcript_controller_runtime.build_exploration_entry(
            base_entry, details=details, status=status
        )

    def _merge_with_latest_exploration_entry(
        self, entry: TranscriptEntry
    ) -> tuple[int, TranscriptEntry] | None:
        return transcript_controller_runtime.merge_with_latest_exploration_entry(self, entry)

    @staticmethod
    def _snapshot_transcript_entries(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
        return transcript_controller_runtime.snapshot_transcript_entries(entries)

    def _sync_transcript(self) -> None:
        transcript_controller_runtime.sync_transcript(self)

    def _refresh_transcript_rendering(self) -> None:
        transcript_controller_runtime.refresh_transcript_rendering(self)

    @staticmethod
    def _transcript_render_width(main_log) -> int:
        return transcript_controller_runtime.transcript_render_width(main_log)

    @staticmethod
    def _prompt_response_turn_events(response: PromptResponse) -> list[dict[str, object]]:
        from cli.agent_cli.models import prompt_response_turn_events

        return prompt_response_turn_events(response)
