import unittest
import tempfile
from pathlib import Path

from reportlab.pdfgen import canvas

from core.ui_utils import merge_results_by_sha, pdf_page_count, preview_widget_key, render_pdf_page


class UiKeyTests(unittest.TestCase):
    def test_duplicate_document_ids_still_generate_unique_keys(self):
        keys = [preview_widget_key(10, position, "abc123") for position in range(3)]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys[0], "preview_10_0_abc123")

    def test_pdf_preview_renders_without_streamlit_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "preview.pdf"
            document = canvas.Canvas(str(pdf_path))
            document.drawString(72, 720, "Vista previa segura")
            document.showPage()
            document.save()
            self.assertEqual(pdf_page_count(pdf_path), 1)
            image = render_pdf_page(pdf_path, 1)
            self.assertTrue(image.startswith(b"\x89PNG"))

    def test_continuing_load_accumulates_and_deduplicates(self):
        first = [{"sha256": "a", "filename": "uno.pdf"}]
        second = [
            {"sha256": "b", "filename": "dos.pdf"},
            {"sha256": "a", "filename": "uno_actualizado.pdf"},
        ]
        merged = merge_results_by_sha(first, second)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["filename"], "uno_actualizado.pdf")
        self.assertEqual(merged[1]["filename"], "dos.pdf")


if __name__ == "__main__":
    unittest.main()
