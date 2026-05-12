from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from internal_policy_docs.library import (
    DEFAULT_LIBRARY_ROOT,
    DEFAULT_RACS_DATA_ROOT,
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
        "description": "Search mounted policy corpora, including PSBC internal policies, laws, regulatory requirements, and standards.",
        "params": ["query", "library_root", "limit"],
    },
    {
        "name": "policy_doc_read",
        "description": "Read normalized Markdown for one imported company policy document by doc_id or path so AI can answer制度 and流程 questions from source text.",
        "params": ["doc_id", "path", "library_root", "max_chars"],
    },
]


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
            "default_external_corpus_root": str(Path(DEFAULT_RACS_DATA_ROOT).resolve()),
            "default_psbc_corpus_root": str(Path(DEFAULT_PSBC_DATA_ROOT).resolve()),
            "default_external_markdown_root": str(Path(DEFAULT_PSBC_MARKDOWN_ROOT).resolve()),
        }

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
