import unittest
import io
import zipfile

from core.text_extract import DocumentPayload, detect_document_year, expand_document_uploads, extract_document


class TextExtractionTests(unittest.TestCase):
    def test_extracts_plain_text(self):
        payload = DocumentPayload("informe.txt", "Informe de gestión mensual".encode("utf-8"))
        extracted = extract_document(payload)
        self.assertIn("Informe de gestión", extracted.text)
        self.assertEqual(extracted.warnings, [])

    def test_rejects_unsupported_type(self):
        payloads, warnings = expand_document_uploads([("archivo.exe", b"x")])
        self.assertEqual(payloads, [])
        self.assertTrue(warnings)

    def test_detects_year_from_filename_over_legal_references(self):
        result = detect_document_year(
            "ACTA_COMITE_2025.pdf",
            "Ley 594 de 2000. Acta celebrada el 15 de marzo de 2025.",
            default_year=2026,
        )
        self.assertEqual(result["year"], "2025")
        self.assertIn("nombre del archivo", result["source"])

    def test_uses_default_year_when_no_date_exists(self):
        result = detect_document_year("informe.pdf", "Contenido sin fecha", default_year=2024)
        self.assertEqual(result["year"], "2024")
        self.assertEqual(result["confidence"], 0.0)

    def test_uses_internal_creation_date_when_available(self):
        result = detect_document_year(
            "informe.pdf",
            "Documento basado en la Ley 594 de 2000.",
            metadata={"created": "2024-05-20T10:30:00"},
            default_year=2026,
        )
        self.assertEqual(result["year"], "2024")
        self.assertIn("creación", result["source"])

    def test_ocr_chooses_most_recent_complete_date(self):
        result = detect_document_year(
            "acta.pdf",
            "Antecedente del 10/01/2023. Acta firmada el 18 de noviembre de 2025.",
            metadata={},
            default_year=2026,
        )
        self.assertEqual(result["year"], "2025")
        self.assertIn("18/11/2025", result["source"])

    def test_zip_timestamp_is_available_for_year_detection(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            info = zipfile.ZipInfo("informe.txt", date_time=(2023, 8, 12, 9, 30, 0))
            archive.writestr(info, "Informe sin fecha visible")
        payloads, warnings = expand_document_uploads([("lote.zip", buffer.getvalue())])
        self.assertEqual(warnings, [])
        self.assertEqual(payloads[0].source_modified_at[:10], "2023-08-12")
        extracted = extract_document(payloads[0])
        result = detect_document_year(payloads[0].name, extracted.text, extracted.metadata, default_year=2026)
        self.assertEqual(result["year"], "2023")
        self.assertIn("ZIP", result["source"])


if __name__ == "__main__":
    unittest.main()
