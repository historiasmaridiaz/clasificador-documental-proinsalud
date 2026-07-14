import unittest
import tempfile

import pandas as pd

from core.ui_utils import preferred_dependency_code, set_boolean_column
from pathlib import Path

from reportlab.pdfgen import canvas

from core.ui_utils import (
    merge_editor_subset,
    merge_results_by_sha,
    ordered_archival_options,
    series_options_for_dependency,
    subseries_options_for_series,
    pdf_page_count,
    preview_widget_key,
    render_pdf_page,
)


class UiKeyTests(unittest.TestCase):
    def test_duplicate_document_ids_still_generate_unique_keys(self):
        keys = [preview_widget_key(10, position, "abc123") for position in range(3)]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys[0], "preview_10_0_abc123")


    def test_archival_options_place_other_first_and_exclude_external_terms(self):
        options = ordered_archival_options(
            ["ACTAS", "INFORMES", "ACTAS", ""],
            "OTROS / OTRAS SERIES — sin código TRD",
        )
        self.assertEqual(options[0], "OTROS / OTRAS SERIES — sin código TRD")
        self.assertEqual(options[1:], ["ACTAS", "INFORMES"])


    def test_hierarchical_options_are_scoped_to_dependency_and_series(self):
        entries = [
            {"dependency_code": "3002.2", "series_name": "ACTAS", "subseries_name": "Actas Comité de Archivo"},
            {"dependency_code": "3002.2", "series_name": "INSTRUMENTOS DE CONTROL", "subseries_name": "Registro de Préstamo de Historias Clínicas"},
            {"dependency_code": "2001.1", "series_name": "INFORMES", "subseries_name": "Informes de Laboratorio"},
        ]
        series = series_options_for_dependency(entries, "3002.2", "OTROS")
        self.assertEqual(series, ["OTROS", "ACTAS", "INSTRUMENTOS DE CONTROL"])
        subseries = subseries_options_for_series(
            entries,
            "3002.2",
            "INSTRUMENTOS DE CONTROL",
            "OTRAS SUBSERIES",
        )
        self.assertEqual(
            subseries,
            ["OTRAS SUBSERIES", "No aplica", "Registro de Préstamo de Historias Clínicas"],
        )
        self.assertNotIn("Informes de Laboratorio", subseries)

    def test_hidden_columns_survive_editor_merge(self):
        base = pd.DataFrame(
            [
                {"id": 1, "Archivo": "uno.pdf", "Serie": "ACTAS", "Evidencia": "oculta"},
                {"id": 2, "Archivo": "dos.pdf", "Serie": "INFORMES", "Evidencia": "oculta 2"},
            ]
        )
        edited = pd.DataFrame(
            [
                {"id": 1, "Archivo": "uno.pdf", "Serie": "INFORMES"},
                {"id": 2, "Archivo": "dos.pdf", "Serie": "INFORMES"},
            ]
        )
        merged = merge_editor_subset(base, edited)
        self.assertEqual(merged.loc[0, "Serie"], "INFORMES")
        self.assertEqual(merged.loc[0, "Evidencia"], "oculta")

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


class ReviewSelectionHelpersTests(unittest.TestCase):
    def test_preferred_dependency_uses_first_visible_catalog_dependency(self):
        records = [
            {"dependency_code": "3002.2"},
            {"dependency_code": "3002.2"},
        ]
        selected = preferred_dependency_code(records, ["1000", "3002.2", "4000"])
        self.assertEqual(selected, "3002.2")

    def test_mark_all_preserves_other_columns(self):
        frame = pd.DataFrame(
            [
                {"id": 1, "Aprobar": False, "Serie": "ACTAS"},
                {"id": 2, "Aprobar": False, "Serie": "INFORMES"},
            ]
        )
        marked = set_boolean_column(frame, "Aprobar", True)
        self.assertTrue(marked["Aprobar"].all())
        self.assertEqual(marked["Serie"].tolist(), ["ACTAS", "INFORMES"])
        self.assertFalse(frame["Aprobar"].any())


if __name__ == "__main__":
    unittest.main()
