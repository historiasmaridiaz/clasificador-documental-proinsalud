import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.exporter import build_classified_zip, manifest_rows, to_pdf_bytes


ENTRIES = [
    {
        "code": "3002.2.28.63",
        "dependency_code": "3002.2",
        "dependency_name": "GESTIÓN DOCUMENTAL",
        "series_code": "28",
        "series_name": "INFORMES",
        "subseries_code": "63",
        "subseries_name": "Informes de Gestión",
        "final_disposition": ["Conservación total"],
    },
    {
        "code": "3006.11",
        "dependency_code": "3006",
        "dependency_name": "CONTABILIDAD",
        "series_code": "11",
        "series_name": "CONCILIACIONES BANCARIAS",
        "subseries_code": "",
        "subseries_name": "",
        "final_disposition": ["Eliminación"],
    },
]


class ExporterTests(unittest.TestCase):
    def test_zip_follows_year_dependency_series_subseries(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "informe.pdf"
            source.write_bytes(b"documento")
            records = [
                {
                    "filename": "informe.pdf",
                    "stored_path": str(source),
                    "extension": ".pdf",
                    "document_year": "2025",
                    "suggested_code": "3002.2.28.63",
                    "final_code": "3002.2.28.63",
                    "suggested_score": 0.88,
                    "confidence": "Alta",
                    "status": "Aprobada",
                    "reviewer_notes": "",
                    "year_source": "nombre del archivo",
                }
            ]
            result = build_classified_zip(records, ENTRIES, include_full_structure=True, years=["2025"])
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                names = archive.namelist()
            expected = (
                "2025/3002.2 - GESTIÓN DOCUMENTAL/3002.2.28 - INFORMES/"
                "3002.2.28.63 - Informes de Gestión/informe.pdf"
            )
            self.assertIn(expected, names)
            self.assertIn("TABLA_CLASIFICACION.pdf", names)

    def test_pdf_report_is_valid(self):
        rows = manifest_rows(
            [
                {
                    "filename": "informe.pdf",
                    "document_year": "2025",
                    "suggested_code": "3002.2.28.63",
                    "final_code": "3002.2.28.63",
                    "suggested_score": 0.88,
                    "confidence": "Alta",
                    "status": "Aprobada",
                    "reviewer_notes": "",
                    "year_source": "OCR",
                }
            ],
            ENTRIES,
        )
        pdf = to_pdf_bytes(rows)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1_000)

    def test_series_without_subseries_does_not_duplicate_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "conciliacion.xlsx"
            source.write_bytes(b"documento")
            records = [
                {
                    "filename": "conciliacion.xlsx",
                    "stored_path": str(source),
                    "document_year": "2025",
                    "suggested_code": "3006.11",
                    "final_code": "3006.11",
                    "suggested_score": 0.91,
                    "confidence": "Alta",
                    "status": "Aprobada",
                    "reviewer_notes": "",
                    "year_source": "contenido",
                }
            ]
            result = build_classified_zip(records, ENTRIES)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                document_path = next(name for name in archive.namelist() if name.endswith("conciliacion.xlsx"))
            self.assertEqual(
                document_path,
                "2025/3006 - CONTABILIDAD/3006.11 - CONCILIACIONES BANCARIAS/conciliacion.xlsx",
            )

    def test_pending_document_is_still_placed_in_suggested_trd_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pendiente.pdf"
            source.write_bytes(b"documento")
            records = [
                {
                    "filename": "pendiente.pdf",
                    "stored_path": str(source),
                    "document_year": "2025",
                    "suggested_code": "3002.2.28.63",
                    "final_code": "3002.2.28.63",
                    "suggested_score": 0.70,
                    "confidence": "Media",
                    "status": "Pendiente",
                    "reviewer_notes": "",
                    "year_source": "OCR",
                }
            ]
            result = build_classified_zip(records, ENTRIES)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                document_path = next(name for name in archive.namelist() if name.endswith("pendiente.pdf"))
            self.assertIn("3002.2.28.63 - Informes de Gestión", document_path)
            self.assertNotIn("PENDIENTES_REVISION", document_path)


if __name__ == "__main__":
    unittest.main()
