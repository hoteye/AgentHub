import sys
import tempfile
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from shared.document_tools.office_tools import OfficeFileTools

class OfficeFileToolsTest(unittest.TestCase):
    def test_excel_and_word_skills(self):
        tools = OfficeFileTools(worker_python=sys.executable)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            xlsx_path = root / "sample.xlsx"
            docx_path = root / "sample.docx"

            created_xlsx = tools.create_xlsx(
                str(xlsx_path),
                sheets=[{"name": "Data", "rows": [["name", "score"], ["alice", 95], ["bob", 88]]}],
            )
            self.assertTrue(created_xlsx["ok"])

            xlsx_summary = tools.read_xlsx_summary(str(xlsx_path))
            self.assertTrue(xlsx_summary["ok"])
            self.assertEqual(xlsx_summary["sheet_names"][0], "Data")
            self.assertEqual(xlsx_summary["sheets"][0]["header"][0], "name")

            updated_xlsx = tools.update_xlsx_cells(
                str(xlsx_path),
                sheet_name="Data",
                updates=[{"cell": "B2", "value": 99}],
            )
            self.assertTrue(updated_xlsx["ok"])

            sheet_rows = tools.read_xlsx_sheet(str(xlsx_path), sheet_name="Data", max_rows=3)
            self.assertTrue(sheet_rows["ok"])
            self.assertEqual(sheet_rows["rows"][1][1], "99")

            created_docx = tools.create_docx(
                str(docx_path),
                title="weekly",
                paragraphs=["first paragraph", "second paragraph"],
            )
            self.assertTrue(created_docx["ok"])

            appended_docx = tools.append_docx_paragraphs(
                str(docx_path),
                heading="extra",
                paragraphs=["third paragraph"],
            )
            self.assertTrue(appended_docx["ok"])

            docx_outline = tools.read_docx_outline(str(docx_path))
            self.assertTrue(docx_outline["ok"])
            self.assertIn("weekly", docx_outline["title"].lower())
            self.assertIn("third paragraph", "\n".join(docx_outline["paragraph_preview"]).lower())

    def test_ingest_spreadsheet_emits_merge_metadata(self):
        tools = OfficeFileTools(worker_python=sys.executable)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            xlsx_path = root / "merged.xlsx"
            runtime_root = root / "runtime"

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Merged"
            sheet["A1"] = "Quarterly Summary"
            sheet.merge_cells("A1:C1")
            sheet["A2"] = "Region"
            sheet["B2"] = "Owner"
            sheet["C2"] = "Status"
            sheet["A3"] = "North"
            sheet["B3"] = "alice"
            sheet["C3"] = "done"
            workbook.save(str(xlsx_path))
            workbook.close()

            ingest = tools.ingest_office_file(str(xlsx_path), runtime_root=str(runtime_root))
            self.assertTrue(ingest["ok"])
            document = ingest["documents"][0]
            self.assertTrue(document["markdown_path"])
            self.assertTrue(document["merge_metadata_path"])

            metadata_path = Path(document["merge_metadata_path"])
            self.assertTrue(metadata_path.exists())
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["sheet_names"][0], "Merged")
            self.assertEqual(metadata["sheets"][0]["merged_cell_count"], 1)
            self.assertEqual(metadata["sheets"][0]["merged_cells"][0]["range"], "A1:C1")
            self.assertEqual(metadata["sheets"][0]["merged_cells"][0]["anchor_value"], "Quarterly Summary")
