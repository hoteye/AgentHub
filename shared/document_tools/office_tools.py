#!/usr/bin/env python3
"""File-level Office skill wrappers for the gateway layer."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


OFFICE_FILE_SKILLS: List[Dict[str, Any]] = [
    {
        "name": "inspect_office_file",
        "category": "general",
        "description": "检查 Office 文件基本信息和类型。",
        "params": ["path"],
    },
    {
        "name": "ingest_office_file",
        "category": "general",
        "description": "解析 docx/xlsx/zip，并输出统一结构化文档结果。",
        "params": ["path", "runtime_root"],
    },
    {
        "name": "read_docx_outline",
        "category": "word",
        "description": "读取 docx 标题、段落预览和表格结构。",
        "params": ["path", "max_paragraphs", "max_tables"],
    },
    {
        "name": "read_docx_markdown",
        "category": "word",
        "description": "将 docx 转成更适合 AI 理解的 Markdown 文档。",
        "params": ["path", "runtime_root"],
    },
    {
        "name": "create_docx",
        "category": "word",
        "description": "创建一个 docx 文档，可带标题和正文段落。",
        "params": ["path", "title", "paragraphs"],
    },
    {
        "name": "append_docx_paragraphs",
        "category": "word",
        "description": "向现有 docx 追加章节标题和正文段落。",
        "params": ["path", "paragraphs", "heading", "save_as"],
    },
    {
        "name": "read_xlsx_summary",
        "category": "excel",
        "description": "读取 xlsx 工作表、表头、样例行和关键单元格摘要。",
        "params": ["path", "max_rows", "max_cols"],
    },
    {
        "name": "read_xls_summary",
        "category": "excel",
        "description": "读取 xls 工作表、表头、样例行和关键单元格摘要。",
        "params": ["path", "max_rows", "max_cols"],
    },
    {
        "name": "read_pdf_markdown",
        "category": "pdf",
        "description": "将 pdf 文本内容转成更适合 AI 理解的 Markdown 文档。",
        "params": ["path", "runtime_root"],
    },
    {
        "name": "read_xlsx_sheet",
        "category": "excel",
        "description": "读取指定工作表的行数据预览。",
        "params": ["path", "sheet_name", "max_rows", "max_cols"],
    },
    {
        "name": "create_xlsx",
        "category": "excel",
        "description": "创建一个 xlsx 文件，可预置多个工作表和数据行。",
        "params": ["path", "sheets"],
    },
    {
        "name": "update_xlsx_cells",
        "category": "excel",
        "description": "按单元格坐标批量更新 xlsx 内容。",
        "params": ["path", "sheet_name", "updates", "save_as"],
    },
]


def _resolve_worker_python(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    env_python = os.environ.get("OFFICE_SKILL_PYTHON")
    if env_python:
        return env_python
    if os.name == "nt":
        return sys.executable
    return shutil.which("python3") or shutil.which("python") or sys.executable or "python3"


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "utf-16", sys.getdefaultencoding()):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").strip()


class OfficeFileTools:
    """Runs file-level Office skills through a dedicated subprocess worker."""

    def __init__(
        self,
        *,
        worker_python: Optional[str] = None,
        worker_script: str = "workers/office_worker.py",
    ):
        self.worker_python = _resolve_worker_python(worker_python)
        root = Path(__file__).resolve().parents[2]
        self.worker_script = str((root / worker_script).resolve())

    def list_skills(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "skills": OFFICE_FILE_SKILLS,
            "count": len(OFFICE_FILE_SKILLS),
            "worker_python": self.worker_python,
        }

    def run_skill(self, skill_name: str, **kwargs: Any) -> Dict[str, Any]:
        cmd = [
            self.worker_python,
            self.worker_script,
            "--skill",
            skill_name,
            "--args-json",
            json.dumps(kwargs, ensure_ascii=False),
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        stdout_text = _decode_output(completed.stdout)
        stderr_text = _decode_output(completed.stderr)
        if completed.returncode != 0:
            return {
                "ok": False,
                "skill": skill_name,
                "error": stderr_text or stdout_text or "office worker failed",
                "worker_python": self.worker_python,
            }
        try:
            result = json.loads(stdout_text)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "skill": skill_name,
                "error": "office worker returned invalid json",
                "raw_output": stdout_text,
                "worker_python": self.worker_python,
            }
        result.setdefault("worker_python", self.worker_python)
        return result

    def inspect_office_file(self, path: str) -> Dict[str, Any]:
        return self.run_skill("inspect_office_file", path=path)

    def ingest_office_file(self, path: str, *, runtime_root: Optional[str] = None) -> Dict[str, Any]:
        return self.run_skill("ingest_office_file", path=path, runtime_root=runtime_root)

    def read_docx_outline(
        self,
        path: str,
        *,
        max_paragraphs: int = 20,
        max_tables: int = 5,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_docx_outline",
            path=path,
            max_paragraphs=max_paragraphs,
            max_tables=max_tables,
        )

    def read_docx_markdown(
        self,
        path: str,
        *,
        runtime_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_docx_markdown",
            path=path,
            runtime_root=runtime_root,
        )

    def create_docx(
        self,
        path: str,
        *,
        title: Optional[str] = None,
        paragraphs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "create_docx",
            path=path,
            title=title,
            paragraphs=paragraphs or [],
        )

    def append_docx_paragraphs(
        self,
        path: str,
        *,
        paragraphs: List[str],
        heading: Optional[str] = None,
        save_as: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "append_docx_paragraphs",
            path=path,
            paragraphs=paragraphs,
            heading=heading,
            save_as=save_as,
        )

    def read_xlsx_summary(
        self,
        path: str,
        *,
        max_rows: int = 12,
        max_cols: int = 12,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_xlsx_summary",
            path=path,
            max_rows=max_rows,
            max_cols=max_cols,
        )

    def read_xls_summary(
        self,
        path: str,
        *,
        max_rows: int = 12,
        max_cols: int = 12,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_xls_summary",
            path=path,
            max_rows=max_rows,
            max_cols=max_cols,
        )

    def read_pdf_markdown(
        self,
        path: str,
        *,
        runtime_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_pdf_markdown",
            path=path,
            runtime_root=runtime_root,
        )

    def read_xlsx_sheet(
        self,
        path: str,
        *,
        sheet_name: Optional[str] = None,
        max_rows: int = 20,
        max_cols: int = 12,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "read_xlsx_sheet",
            path=path,
            sheet_name=sheet_name,
            max_rows=max_rows,
            max_cols=max_cols,
        )

    def create_xlsx(
        self,
        path: str,
        *,
        sheets: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "create_xlsx",
            path=path,
            sheets=sheets or [],
        )

    def update_xlsx_cells(
        self,
        path: str,
        *,
        sheet_name: str,
        updates: List[Dict[str, Any]],
        save_as: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.run_skill(
            "update_xlsx_cells",
            path=path,
            sheet_name=sheet_name,
            updates=updates,
            save_as=save_as,
        )
