#!/usr/bin/env python3
"""File-level Office worker executed as a subprocess by gateway tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from workers.office_worker_document_helpers import (  # noqa: E402
    _ingest_office_file,
    _read_docx_markdown,
    _read_pdf_markdown,
)
from workers.office_worker_office_helpers import (  # noqa: E402
    _append_docx_paragraphs,
    _create_docx,
    _create_xlsx,
    _inspect_office_file,
    _read_docx_outline,
    _read_xls_summary,
    _read_xlsx_sheet,
    _read_xlsx_summary,
    _update_xlsx_cells,
)


SKILLS = {
    "inspect_office_file": _inspect_office_file,
    "ingest_office_file": _ingest_office_file,
    "read_docx_outline": _read_docx_outline,
    "read_docx_markdown": _read_docx_markdown,
    "read_pdf_markdown": _read_pdf_markdown,
    "read_xlsx_summary": _read_xlsx_summary,
    "read_xls_summary": _read_xls_summary,
    "read_xlsx_sheet": _read_xlsx_sheet,
    "update_xlsx_cells": _update_xlsx_cells,
    "create_xlsx": _create_xlsx,
    "create_docx": _create_docx,
    "append_docx_paragraphs": _append_docx_paragraphs,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gateway Office worker")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--args-json", default="{}")
    args = parser.parse_args()

    skill = SKILLS.get(args.skill)
    if skill is None:
        raise SystemExit(json.dumps({"ok": False, "error": f"unknown skill: {args.skill}"}, ensure_ascii=False))

    payload = json.loads(args.args_json)
    result = skill(**payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
