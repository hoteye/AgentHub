from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import PromptAttachment
from cli.agent_cli.providers.policy_routing import (
    looks_like_policy_context,
    looks_like_policy_question,
)
from cli.agent_cli.workspace_context import (
    render_explicit_skill_injections,
    render_workspace_reference_context_item_message,
)


class PlannerInputItemsMixin:
    def _tool_spec_names(self) -> set[str]:
        specs: List[Dict[str, Any]] = []
        direct_getter = getattr(self, "_tool_specs", None)
        if callable(direct_getter):
            try:
                specs = list(direct_getter() or [])
            except Exception:
                specs = []
        if not specs:
            builder = (
                getattr(self, "_turn_engine_tool_specs_builder", None)
                or getattr(self, "_direct_loop_tool_specs_builder", None)
            )
            if callable(builder):
                try:
                    specs = list(
                        builder(
                            self.config,
                            self.host_platform,
                            plugin_manager_factory=self.plugin_manager_factory,
                        )
                        or []
                    )
                except TypeError:
                    try:
                        specs = list(builder(self.config, self.host_platform) or [])
                    except Exception:
                        specs = []
                except Exception:
                    specs = []
        names: set[str] = set()
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "").strip()
            if not name:
                nested = spec.get("function")
                if isinstance(nested, dict):
                    name = str(nested.get("name") or "").strip()
            if name:
                names.add(name)
        return names

    def _policy_qa_guidance_enabled(self) -> bool:
        names = self._tool_spec_names()
        return "policy_doc_search" in names and "policy_doc_read" in names

    def _should_apply_policy_qa_guidance(self, user_text: str) -> bool:
        return self._policy_qa_guidance_enabled() and looks_like_policy_question(user_text)

    @staticmethod
    def _attachment_payloads(attachments: Optional[List[PromptAttachment]]) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in list(attachments or [])]

    @staticmethod
    def _message_input_item(role: str, content: str) -> Dict[str, Any]:
        return {
            "type": "message",
            "role": str(role or "user").strip() or "user",
            "content": [
                {
                    "type": "input_text",
                    "text": str(content or ""),
                }
            ],
        }

    @staticmethod
    def _message_input_item_with_blocks(role: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "type": "message",
            "role": str(role or "user").strip() or "user",
            "content": [dict(block) for block in content],
        }

    @classmethod
    def _input_item_content_blocks(cls, role: str, content: Any) -> List[Dict[str, Any]]:
        if not isinstance(content, list):
            return []
        normalized_role = str(role or "user").strip().lower() or "user"
        default_type = "output_text" if normalized_role == "assistant" else "input_text"
        blocks: List[Dict[str, Any]] = []
        for entry in content:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    blocks.append({"type": default_type, "text": text})
                continue
            if not isinstance(entry, dict):
                continue
            block = dict(entry)
            block_type = str(block.get("type") or "").strip()
            if not block_type:
                text = str(block.get("text") or "").strip()
                if text:
                    blocks.append({"type": default_type, "text": text})
                continue
            if block_type in {"input_text", "text", "output_text"}:
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                block["text"] = text
            blocks.append(block)
        return blocks

    @classmethod
    def _input_item_text(cls, item: Dict[str, Any]) -> str:
        content = item.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for entry in content:
                if isinstance(entry, str):
                    if entry.strip():
                        parts.append(entry)
                    continue
                if not isinstance(entry, dict):
                    continue
                entry_type = str(entry.get("type") or "").strip()
                if entry_type in {"input_text", "text", "output_text"}:
                    text = str(entry.get("text") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(content or "").strip()

    @classmethod
    def _response_item_message(cls, item: Dict[str, Any]) -> Dict[str, Any] | None:
        content_source = item.get("item") or item
        if not isinstance(content_source, dict):
            return None
        role = str(
            content_source.get("role")
            or content_source.get("item_role")
            or item.get("role")
            or "assistant"
        ).strip() or "assistant"
        text = cls._input_item_text(content_source)
        if not text:
            return None
        return {"role": role, "content": text}

    @classmethod
    def _normalize_input_items(cls, items: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw in list(items or []):
            if not isinstance(raw, dict):
                continue
            item_type = str(raw.get("type") or "").strip()
            if item_type == "message":
                role = str(raw.get("role") or "user").strip() or "user"
                blocks = cls._input_item_content_blocks(role, raw.get("content"))
                if len(blocks) > 1:
                    normalized.append(cls._message_input_item_with_blocks(role, blocks))
                    continue
                text = cls._input_item_text(raw)
                if text:
                    normalized.append(cls._message_input_item(role, text))
                continue
            if item_type in {"response_item", "reference_context_item", "state_snapshot", "function_call_output", "custom_tool_call_output"}:
                normalized.append(dict(raw))
                continue
            if "role" in raw and "content" in raw and not item_type:
                role = str(raw.get("role") or "user").strip() or "user"
                blocks = cls._input_item_content_blocks(role, raw.get("content"))
                if len(blocks) > 1:
                    normalized.append(cls._message_input_item_with_blocks(role, blocks))
                    continue
                text = cls._input_item_text(raw)
                if text:
                    normalized.append(cls._message_input_item(role, text))
                continue
            role = str(raw.get("role") or "").strip().lower()
            content = str(raw.get("content") or "").strip()
            if role and content:
                normalized.append(cls._message_input_item(role, content))
                continue
            if item_type:
                normalized.append(dict(raw))
        return normalized

    @classmethod
    def _input_items_have_assistant_turn(cls, items: Optional[List[Dict[str, Any]]]) -> bool:
        for item in cls._normalize_input_items(items):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip()
            if item_type in {"function_call_output", "custom_tool_call_output"}:
                return True
            if item_type == "response_item":
                role = str(item.get("role") or "").strip().lower()
                if role == "assistant":
                    return True
                nested = item.get("item")
                if isinstance(nested, dict):
                    nested_role = str(nested.get("role") or nested.get("item_role") or "").strip().lower()
                    if nested_role == "assistant":
                        return True
                continue
            role = str(item.get("role") or "").strip().lower()
            if role == "assistant":
                return True
        return False

    def _conversation_input_items(
        self,
        user_text: str,
        history: List[Dict[str, str]],
        *,
        attachments: Optional[List[PromptAttachment]] = None,
        input_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        items = self._normalize_input_items(input_items)
        relevant = self._relevant_history(user_text, history)
        if not self._input_items_have_assistant_turn(items):
            for item in relevant:
                role = str(item.get("role") or "user")
                content = str(item.get("content") or "").strip()
                if content:
                    items.append(self._message_input_item(role, content))
        items.append(self._message_input_item("user", self._compose_user_text(user_text, attachments)))
        return items

    @classmethod
    def _chat_messages_from_input_items(
        cls,
        input_items: List[Dict[str, Any]],
        *,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for item in cls._normalize_input_items(input_items):
            item_type = str(item.get("type") or "").strip()
            if item_type == "response_item":
                message = cls._response_item_message(item)
                if message:
                    messages.append(message)
                continue
            if item_type == "reference_context_item":
                payload = item.get("item")
                if isinstance(payload, dict):
                    rendered = render_workspace_reference_context_item_message(payload)
                    if rendered:
                        messages.append({"role": "user", "content": rendered})
                continue
            role = str(item.get("role") or "user").strip() or "user"
            text = cls._input_item_text(item)
            if text:
                messages.append({"role": role, "content": text})
        return messages

    def _compose_user_text(self, user_text: str, attachments: Optional[List[PromptAttachment]]) -> str:
        payloads = self._attachment_payloads(attachments)
        parts = [str(user_text or "")]
        if self._should_apply_policy_qa_guidance(user_text):
            parts.extend(
                [
                    "",
                    "POLICY_QA_HINT:",
                    "- Use policy_doc_search first with 2 to 4 short queries; do not paste the full long question verbatim.",
                    "- Break each query into target terms, action terms, and policy terms, such as account, permission, application, lockout, review, audit, or deprovisioning.",
                    "- After you hit formal policy documents, use policy_doc_read to read the 1 to 3 most relevant source documents.",
                    "- Base the final answer only on policy evidence that was actually found or read.",
                ]
            )
        if payloads:
            parts.extend(
                [
                    "",
                    "ATTACHMENTS_JSON:",
                    json.dumps(payloads, ensure_ascii=False, indent=2),
                    "",
                    "The JSON above contains structured local attachment objects for this turn. Use attachment.path when you need to read or analyze a local file.",
                ]
            )
        skill_injections = render_explicit_skill_injections(
            user_text,
            self.cwd,
            extra_skill_roots=self._plugin_skill_roots(),
        )
        if skill_injections:
            parts.extend(["", skill_injections])
        return "\n".join(parts).strip()

    def _relevant_history(self, user_text: str, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        items = list(history or [])
        if not self._should_apply_policy_qa_guidance(user_text):
            return items[-10:]
        filtered = [
            item
            for item in items
            if looks_like_policy_context(str(item.get("content") or ""))
        ]
        return filtered[-10:]
