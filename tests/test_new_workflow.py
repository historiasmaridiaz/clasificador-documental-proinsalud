from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from core.database import Database
from core.exporter import build_classified_zip, manifest_rows
from core.text_extract import DocumentPayload, ExtractedDocument


ENTRY = {
    "code": "3002.2.28.63",
    "dependency_code": "3002.2",
    "dependency_name": "GESTIÓN DOCUMENTAL",
    "series_code": "28",
    "series_name": "INFORMES",
    "subseries_code": "63",
    "subseries_name": "Informes de Gestión",
    "document_types": ["Informe", "Anexos"],
    "retention_management": "2",
    "retention_central": "8",
    "final_disposition": ["Conservación total"],
}


class NewWorkflowTests(unittest.TestCase):
    def test_custom_other_classification_is_persisted_and_manifested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(tmp)
            catalog_id = db.save_catalog("Inicial", [ENTRY])
            payload = DocumentPayload("documento_atipico.txt", b"contenido fuera de tabla")
            extracted = ExtractedDocument(
                payload.name,
                "contenido fuera de tabla",
                payload.sha256,
                ".txt",
            )
            document_id = db.save_document(payload, extracted)
            classification_id = db.save_classification(document_id, catalog_id, [])
            custom = {
                "is_other": True,
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_name": "OTROS / OTRAS SERIES — clasificación temporal",
            }
            db.update_review(
                classification_id,
                "",
                "Corregida",
                "Fuera de la TRD",
                document_year=2026,
                custom_classification=custom,
            )
            record = db.list_classifications()[0]
            self.assertTrue(record["custom_classification"]["is_other"])
            row = manifest_rows([record], [ENTRY])[0]
            self.assertEqual(row["codigo_final"], "")
            self.assertIn("OTROS", row["serie"])
            self.assertEqual(row["dependencia"], "GESTIÓN DOCUMENTAL")

    def test_catalog_can_be_deleted_or_archived_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(tmp)
            first = db.save_catalog("Primero", [ENTRY])
            second = db.save_catalog("Segundo", [ENTRY])
            self.assertEqual(db.delete_catalog(first), "deleted")
            self.assertEqual(db.active_catalog()["id"], second)
            with self.assertRaises(ValueError):
                db.delete_catalog(second)

    def test_massive_template_places_document_in_coded_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "informe.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF")
            template = root / "template.zip"
            with zipfile.ZipFile(template, "w") as archive:
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/", b"")
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/", b"")
                archive.writestr("CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/3002.2.28 - INFORMES/", b"")
                archive.writestr(
                    "CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/3002.2.28 - INFORMES/3002.2.28.63 - Informes de Gestión/",
                    b"",
                )
                archive.writestr(
                    "CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/3002.2.28 - INFORMES/3002.2.28.63 - Informes de Gestión/Informe/",
                    b"",
                )
            record = {
                "filename": source.name,
                "stored_path": str(source),
                "final_code": ENTRY["code"],
                "suggested_code": ENTRY["code"],
                "suggested_score": 0.8,
                "confidence": "Alta",
                "document_year": "2026",
                "status": "Aprobada",
                "extracted_text": "Informe de gestión institucional",
                "custom_classification": {},
            }
            data = build_classified_zip(
                [record],
                [ENTRY],
                include_full_structure=True,
                structure_mode="massive",
                template_zip_path=template,
                organize_by_document_type=True,
            )
            output = root / "out.zip"
            output.write_bytes(data)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            self.assertIn(
                "CARPETAS_MASIVAS_ACTUALIZADAS/3002.2 - GESTIÓN DOCUMENTAL/3002.2.28 - INFORMES/3002.2.28.63 - Informes de Gestión/Informe/informe.pdf",
                names,
            )


if __name__ == "__main__":
    unittest.main()
