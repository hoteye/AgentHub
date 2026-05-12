from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from internal_policy_docs.library import (
    DEFAULT_LIBRARY_ROOT,
    DEFAULT_PSBC_DATA_ROOT,
    DEFAULT_PSBC_MARKDOWN_ROOT,
    import_policy_documents,
    list_policy_documents,
    read_policy_markdown,
    search_policy_documents,
)


INTERNAL_POLICY_DOC_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "policy_doc_import",
        "description": "Import local PSBC policy or制度 files from .doc/.docx/.pdf into the managed Markdown library for later rule lookup and AI retrieval.",
        "params": ["path", "library_root", "recursive"],
    },
    {
        "name": "policy_doc_list",
        "description": "List imported company policy and制度 documents from the managed Markdown library.",
        "params": ["library_root", "limit"],
    },
    {
        "name": "policy_doc_search",
        "description": "Search imported PSBC policy Markdown by 外包管理, 开发测试, 运维运行, 安全配置, 数据分类分级, CMDB, 技术评审, 差旅培训, 内部聊天账号管理, 制度名称, 流程, and other body text.",
        "params": ["query", "library_root", "limit"],
    },
    {
        "name": "policy_doc_read",
        "description": "Read normalized Markdown for one imported company policy document by doc_id or path so AI can answer制度 and流程 questions from source text.",
        "params": ["doc_id", "path", "library_root", "max_chars"],
    },
]


def _structured_result(
    *,
    tool_name: str,
    payload: Dict[str, Any],
    assistant_text: str,
    arguments: Optional[Dict[str, Any]] = None,
    summary: str = "",
) -> CommandExecutionResult:
    normalized_payload = dict(payload or {})
    ok = bool(normalized_payload.get("ok"))
    resolved_summary = str(summary or "").strip() or (
        f"{tool_name} ok" if ok else f"{tool_name} failed"
    )
    event = ToolEvent(
        name=tool_name,
        ok=ok,
        summary=resolved_summary,
        payload=normalized_payload,
    )
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=tool_name,
            arguments=dict(arguments or {}) or None,
            ok=ok,
            summary=resolved_summary,
            structured_content=normalized_payload,
        ),
    )


class InternalPolicyTools:
    @staticmethod
    def _failure(action: str, exc: Exception) -> Dict[str, Any]:
        return {
            "ok": False,
            "action": action,
            "error": f"{type(exc).__name__}: {exc}",
            "default_library_root": str(Path(DEFAULT_LIBRARY_ROOT).resolve()),
        }

    def list_skills(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "count": len(INTERNAL_POLICY_DOC_SKILLS),
            "skills": INTERNAL_POLICY_DOC_SKILLS,
            "default_library_root": str(Path(DEFAULT_LIBRARY_ROOT).resolve()),
            "default_external_corpus_root": str(Path(DEFAULT_PSBC_DATA_ROOT).resolve()),
            "default_external_markdown_root": str(Path(DEFAULT_PSBC_MARKDOWN_ROOT).resolve()),
        }

    def list_skills_result(self) -> CommandExecutionResult:
        payload = self.list_skills()
        return _structured_result(
            tool_name="policy_doc_list",
            payload=payload,
            assistant_text="List internal policy document skills.",
            summary=f"policy skills={int(payload.get('count') or 0)}",
        )

    def policy_doc_import(
        self,
        path: str,
        *,
        library_root: Optional[str] = None,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        try:
            return import_policy_documents(path, library_root=library_root, recursive=recursive)
        except Exception as exc:
            return self._failure("policy_doc_import", exc)

    def policy_doc_import_result(
        self,
        path: str,
        *,
        library_root: Optional[str] = None,
        recursive: bool = True,
    ) -> CommandExecutionResult:
        payload = self.policy_doc_import(path, library_root=library_root, recursive=recursive)
        return _structured_result(
            tool_name="policy_doc_import",
            payload=payload,
            assistant_text="Import internal policy documents.",
            arguments={
                "path": path,
                "library_root": library_root,
                "recursive": bool(recursive),
            },
            summary=f"policy docs imported={int(payload.get('imported_count') or 0)}"
            if bool(payload.get("ok"))
            else "policy import failed",
        )

    def policy_doc_list(
        self,
        *,
        library_root: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        try:
            return list_policy_documents(library_root=library_root, limit=limit)
        except Exception as exc:
            return self._failure("policy_doc_list", exc)

    def policy_doc_list_result(
        self,
        *,
        library_root: Optional[str] = None,
        limit: int = 50,
    ) -> CommandExecutionResult:
        payload = self.policy_doc_list(library_root=library_root, limit=limit)
        return _structured_result(
            tool_name="policy_doc_list",
            payload=payload,
            assistant_text="List internal policy documents.",
            arguments={"library_root": library_root, "limit": int(limit)},
            summary=f"policy docs={int(payload.get('count') or 0)}"
            if bool(payload.get("ok"))
            else "policy list failed",
        )

    def policy_doc_search(
        self,
        query: str,
        *,
        library_root: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        try:
            return search_policy_documents(query, library_root=library_root, limit=limit)
        except Exception as exc:
            return self._failure("policy_doc_search", exc)

    def policy_doc_search_result(
        self,
        query: str,
        *,
        library_root: Optional[str] = None,
        limit: int = 10,
    ) -> CommandExecutionResult:
        payload = self.policy_doc_search(query, library_root=library_root, limit=limit)
        return _structured_result(
            tool_name="policy_doc_search",
            payload=payload,
            assistant_text="Search internal policy documents.",
            arguments={"query": query, "library_root": library_root, "limit": int(limit)},
            summary=f"policy matches={int(payload.get('count') or 0)}"
            if bool(payload.get("ok"))
            else "policy search failed",
        )

    def policy_doc_read(
        self,
        *,
        doc_id: Optional[str] = None,
        path: Optional[str] = None,
        library_root: Optional[str] = None,
        max_chars: int = 12000,
    ) -> Dict[str, Any]:
        try:
            return read_policy_markdown(doc_id=doc_id, path=path, library_root=library_root, max_chars=max_chars)
        except Exception as exc:
            return self._failure("policy_doc_read", exc)

    def policy_doc_read_result(
        self,
        *,
        doc_id: Optional[str] = None,
        path: Optional[str] = None,
        library_root: Optional[str] = None,
        max_chars: int = 12000,
    ) -> CommandExecutionResult:
        payload = self.policy_doc_read(
            doc_id=doc_id,
            path=path,
            library_root=library_root,
            max_chars=max_chars,
        )
        return _structured_result(
            tool_name="policy_doc_read",
            payload=payload,
            assistant_text="Read internal policy markdown.",
            arguments={
                "doc_id": doc_id,
                "path": path,
                "library_root": library_root,
                "max_chars": int(max_chars),
            },
            summary="policy markdown loaded" if bool(payload.get("ok")) else "policy markdown read failed",
        )
