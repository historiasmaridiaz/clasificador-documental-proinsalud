from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.database import Database
from core.text_extract import DocumentPayload, ExtractedDocument


LONG_NAME = (
    "Instructivo_INSTRUCTIVO_PARA_LA_INTERPRETACION_Y_USO_DE_LA_TABLA_DE_"
    "RETENCION_DOCUMENTAL__TRD__Y_EL_CUADRO_DE_CLASIFICACION_DOCUMENTAL__CCD_.pdf"
)


class DatabaseStorageTests(unittest.TestCase):
    def test_recreates_upload_directory_before_saving(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(tmp)
            db.upload_dir.rmdir()
            payload = DocumentPayload(LONG_NAME, b"%PDF-1.4\n%%EOF")
            extracted = ExtractedDocument(payload.name, "Instructivo TRD y CCD", payload.sha256, ".pdf")

            document_id = db.save_document(payload, extracted)

            self.assertGreater(document_id, 0)
            files = list(db.upload_dir.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), payload.data)

    def test_long_original_name_is_stored_with_a_short_safe_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(tmp)
            payload = DocumentPayload(LONG_NAME, b"%PDF-1.4\n%%EOF")
            extracted = ExtractedDocument(payload.name, "Instructivo TRD y CCD", payload.sha256, ".pdf")
            catalog_id = db.save_catalog(
                "Prueba",
                [
                    {
                        "code": "3002.2.30.293",
                        "dependency_code": "3002.2",
                        "dependency_name": "GESTIÓN DOCUMENTAL",
                        "series_code": "30",
                        "series_name": "INSTRUMENTOS DE CONTROL",
                        "subseries_code": "293",
                        "subseries_name": "Instrumentos de Control de Temperatura y Humedad",
                    }
                ],
            )

            document_id = db.save_document(payload, extracted)
            db.save_classification(document_id, catalog_id, [])
            record = db.list_classifications()[0]
            stored_path = Path(record["stored_path"])

            self.assertTrue(stored_path.exists())
            self.assertEqual(stored_path.suffix.lower(), ".pdf")
            self.assertLessEqual(len(stored_path.name), 113)  # hash + guion bajo + 96 caracteres
            self.assertEqual(record["filename"], LONG_NAME)


    def test_existing_classification_can_be_updated_without_binding_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(tmp)
            payload = DocumentPayload("actualizable.pdf", b"%PDF-1.4\n%%EOF")
            extracted = ExtractedDocument(payload.name, "Documento actualizable", payload.sha256, ".pdf")
            catalog_id = db.save_catalog(
                "Prueba actualización",
                [
                    {
                        "code": "3002.2.2.7",
                        "dependency_code": "3002.2",
                        "dependency_name": "GESTIÓN DOCUMENTAL",
                        "series_code": "2",
                        "series_name": "ACTAS",
                        "subseries_code": "7",
                        "subseries_name": "Actas Comité de Historias Clínicas",
                    }
                ],
            )
            document_id = db.save_document(payload, extracted)
            db.save_classification(document_id, catalog_id, [])
            db.save_classification(
                document_id,
                catalog_id,
                [
                    {
                        "code": "3002.2.2.7",
                        "score": 0.91,
                        "confidence": "Alta",
                    }
                ],
                document_year="2026",
                year_source="contenido",
                year_confidence=0.9,
            )
            record = db.list_classifications()[0]
            self.assertEqual(record["suggested_code"], "3002.2.2.7")
            self.assertAlmostEqual(record["suggested_score"], 0.91)


if __name__ == "__main__":
    unittest.main()
