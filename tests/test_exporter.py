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


class MassiveFolderRegressionTests(unittest.TestCase):
    def test_long_template_path_does_not_create_a_second_truncated_folder(self):
        entry = {
            "code": "3002.2.30.293",
            "dependency_code": "3002.2",
            "dependency_name": "GESTIÓN DOCUMENTAL",
            "series_code": "30",
            "series_name": "INSTRUMENTOS DE CONTROL",
            "subseries_code": "293",
            "subseries_name": "Instrumentos de Control de Temperatura y Humedad",
            "document_types": ["Control de temperatura y humedad relativa en archivo"],
            "final_disposition": ["Conservación total"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / ("registro_control_temperatura_humedad_archivo_central_" + "x" * 90 + ".pdf")
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            template = root / "template.zip"
            base = (
                "CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/"
                "3002.2.30 - INSTRUMENTOS DE CONTROL/"
                "3002.2.30.293 - Instrumentos de Control de Temperatura y Humedad/"
            )
            type_folder = "Control de temperatura y humedad relativa en archivo"
            with zipfile.ZipFile(template, "w") as archive:
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/", b"")
                archive.writestr(base, b"")
                archive.writestr(base + type_folder + "/", b"")
            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": entry["code"],
                "suggested_code": entry["code"],
                "suggested_score": 0.95,
                "confidence": "Alta",
                "document_year": "2026",
                "status": "Aprobada",
                "extracted_text": "control de temperatura y humedad relativa en archivo",
                "custom_classification": {},
            }
            data = build_classified_zip(
                [record],
                [entry],
                include_full_structure=True,
                structure_mode="massive",
                template_zip_path=template,
                organize_by_document_type=True,
            )
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            document_path = next(name for name in names if name.lower().endswith(".pdf") and not name.startswith("TABLA_"))
            self.assertIn(f"/{type_folder}/", document_path)
            sibling_components = {
                name[len(base):].split("/", 1)[0]
                for name in names
                if name.startswith(base) and name[len(base):]
            }
            self.assertEqual(sibling_components, {type_folder})

    def test_banter_custom_classification_creates_named_uncoded_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "control_ambiental.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": "",
                "suggested_code": "",
                "suggested_score": 0.72,
                "confidence": "Media",
                "document_year": "2026",
                "status": "Corregida",
                "custom_classification": {
                    "is_other": True,
                    "is_banter": True,
                    "source": "BANTER AGN — referencia orientativa",
                    "dependency_code": "3002.2",
                    "dependency_name": "GESTIÓN DOCUMENTAL",
                    "series_name": "INSTRUMENTOS DE CONTROL",
                    "subseries_name": "Instrumentos de Control de Temperatura y Humedad",
                    "document_types": [],
                },
            }
            data = build_classified_zip([record], [], structure_mode="massive")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                document_path = next(name for name in archive.namelist() if name.endswith("control_ambiental.pdf"))
            self.assertIn("SERIE SIN CÓDIGO - INSTRUMENTOS DE CONTROL", document_path)
            self.assertIn(
                "SUBSERIE SIN CÓDIGO - Instrumentos de Control de Temperatura y Humedad",
                document_path,
            )


class OfficialFolderCanonicalizationTests(unittest.TestCase):
    def test_banter_series_does_not_duplicate_existing_coded_series_folder(self):
        official_entry = {
            "code": "3002.2.29.381",
            "dependency_code": "3002.2",
            "dependency_name": "GESTIÓN DOCUMENTAL",
            "series_code": "29",
            "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
            "subseries_code": "381",
            "subseries_name": "Tablas de Retención Documental",
            "document_types": ["Tabla de retención documental"],
            "final_disposition": ["Conservación total"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "instrumento.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            template = root / "template.zip"
            official_series = (
                "CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/"
                "3002.2.29 - INSTRUMENTOS ARCHIVÍSTICOS/"
            )
            with zipfile.ZipFile(template, "w") as archive:
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/", b"")
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/", b"")
                archive.writestr(official_series, b"")

            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": "",
                "suggested_code": "",
                "suggested_score": 0.72,
                "confidence": "Media",
                "document_year": "2026",
                "status": "Aprobada",
                "extracted_text": "instrumentos archivísticos",
                "custom_classification": {
                    "is_other": True,
                    "is_banter": True,
                    "source": "BANTER AGN — referencia orientativa",
                    "dependency_code": "3002.2",
                    "dependency_name": "GESTIÓN DOCUMENTAL",
                    "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
                    "subseries_name": "",
                    "document_types": [],
                },
            }
            data = build_classified_zip(
                [record],
                [official_entry],
                include_full_structure=True,
                structure_mode="massive",
                template_zip_path=template,
                organize_by_document_type=False,
            )
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            document_path = next(name for name in names if name.endswith("instrumento.pdf"))
            self.assertTrue(document_path.startswith(official_series))
            self.assertFalse(any("SERIE SIN CÓDIGO - INSTRUMENTOS ARCHIVÍSTICOS" in name for name in names))


class UnclassifiedOtherFolderTests(unittest.TestCase):
    def test_unidentified_document_creates_other_series_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "documento_desconocido.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": "",
                "suggested_code": "",
                "suggested_score": 0.0,
                "confidence": "Revisión requerida",
                "document_year": "2026",
                "status": "Aprobada",
                "candidates": [],
                "custom_classification": {},
            }
            data = build_classified_zip([record], [], structure_mode="massive")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            expected_folder = (
                "CARPETAS_MASIVAS_ACTUALIZADAS/"
                "OTROS - DEPENDENCIA POR DEFINIR/"
                "OTROS - OTRAS SERIES SIN CÓDIGO TRD/"
            )
            self.assertIn(expected_folder, names)
            self.assertIn(expected_folder + source.name, names)
            self.assertFalse(any("SIN_CLASIFICACION" in name for name in names))

    def test_unidentified_document_keeps_candidate_dependency_but_uses_other_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "documento_fuera_trd.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": "",
                "suggested_code": "CODIGO_ANTIGUO",
                "suggested_score": 0.12,
                "confidence": "Baja",
                "document_year": "2026",
                "status": "Corregida",
                "candidates": [
                    {
                        "dependency_code": "3002.2",
                        "dependency_name": "GESTIÓN DOCUMENTAL",
                        "series_name": "SERIE NO VIGENTE",
                    }
                ],
                "custom_classification": {},
            }
            data = build_classified_zip([record], [], structure_mode="massive")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            expected_folder = (
                "CARPETAS_MASIVAS_ACTUALIZADAS/"
                "3002.2 - GESTIÓN DOCUMENTAL/"
                "OTROS - OTRAS SERIES SIN CÓDIGO TRD/"
            )
            self.assertIn(expected_folder, names)
            self.assertIn(expected_folder + source.name, names)
