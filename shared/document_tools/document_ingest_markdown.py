from __future__ import annotations

from typing import Dict, List


def _render_docx_markdown(content: Dict) -> str:
    lines: List[str] = []
    title = (content.get("title") or "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")
    for paragraph in content.get("paragraph_preview", []) or []:
        text = str(paragraph).strip()
        if not text:
            continue
        lines.append(text)
        lines.append("")
    for table_index, table in enumerate(content.get("tables", []) or [], start=1):
        rows = table.get("rows") or []
        if not rows:
            continue
        lines.append(f"## Table {table_index}")
        header = [str(cell or "").strip() for cell in rows[0]]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in rows[1:]:
            values = [str(cell or "").strip() for cell in row]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_sheet_markdown(sheet: Dict) -> List[str]:
    lines: List[str] = [f"## {sheet.get('sheet_name') or 'Sheet'}", ""]
    merged_count = int(sheet.get("merged_cell_count") or 0)
    if merged_count:
        lines.append(f"Merged Cells: {merged_count}")
        for merged in (sheet.get("merged_cells_preview") or [])[:8]:
            anchor = str(merged.get("anchor_value") or "").strip() or "(empty)"
            lines.append(
                f"- `{merged.get('range')}` rows={merged.get('row_span')} cols={merged.get('col_span')} anchor={anchor}"
            )
        lines.append("")
    header = [str(cell or "").strip() for cell in sheet.get("header", [])]
    sample_rows = sheet.get("sample_rows", []) or []
    if any(header):
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in sample_rows[:8]:
            values = [str(cell or "").strip() for cell in row[: len(header)]]
            if len(values) < len(header):
                values.extend([""] * (len(header) - len(values)))
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    key_cells = sheet.get("key_cells") or {}
    if key_cells:
        lines.append("Key Cells:")
        for key, value in list(key_cells.items())[:12]:
            lines.append(f"- `{key}`: {value}")
        lines.append("")
    return lines


def _render_spreadsheet_markdown(content: Dict, *, title: str) -> str:
    lines: List[str] = [f"# {title}", ""]
    sheet_names = content.get("sheet_names") or []
    if sheet_names:
        lines.append("Sheets:")
        for name in sheet_names:
            lines.append(f"- {name}")
        lines.append("")
    for sheet in content.get("sheets", []) or []:
        lines.extend(_render_sheet_markdown(sheet))
    if any(int(sheet.get("merged_cell_count") or 0) for sheet in content.get("sheets", []) or []):
        lines.append("Merged-cell structure is preserved in the companion merge_metadata.json artifact.")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_pdf_markdown(content: Dict) -> str:
    lines: List[str] = []
    title = (content.get("title") or "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")
    lines.append(f"- Pages: {content.get('page_count') or 0}")
    metadata = content.get("metadata") or {}
    if metadata.get("author"):
        lines.append(f"- Author: {metadata['author']}")
    if metadata.get("subject"):
        lines.append(f"- Subject: {metadata['subject']}")
    lines.append("")
    for page in content.get("pages", []) or []:
        lines.append(f"## Page {page.get('page_number')}")
        lines.append("")
        text = str(page.get("text_preview") or "").strip()
        if text:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_markdown(file_type: str, content: Dict, *, title: str) -> str:
    if file_type == "docx":
        return _render_docx_markdown(content)
    if file_type in {"xlsx", "xls"}:
        return _render_spreadsheet_markdown(content, title=title)
    if file_type == "pdf":
        return _render_pdf_markdown(content)
    return ""
