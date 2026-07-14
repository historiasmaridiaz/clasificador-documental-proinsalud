import unittest

from core.ml_engine import DocumentClassifier


CATALOG = [
    {
        "code": "1004.13.31",
        "dependency_code": "1004",
        "dependency_name": "JURÍDICA",
        "series_name": "CONTRATOS",
        "subseries_name": "Contratos de Arrendamiento",
        "document_types": ["Contrato", "Póliza", "Acta de liquidación"],
        "procedure": "",
    },
    {
        "code": "1006.25",
        "dependency_code": "1006",
        "dependency_name": "TALENTO HUMANO",
        "series_name": "HISTORIAS LABORALES",
        "subseries_name": "",
        "document_types": ["Hoja de vida", "Contrato laboral", "Certificados"],
        "procedure": "",
    },
    {
        "code": "3006.11",
        "dependency_code": "3006",
        "dependency_name": "CONTABILIDAD",
        "series_name": "CONCILIACIONES BANCARIAS",
        "subseries_name": "",
        "document_types": ["Extracto bancario", "Conciliación"],
        "procedure": "",
    },
]


class MachineLearningTests(unittest.TestCase):
    def test_contract_query_ranks_contract_series_first(self):
        model = DocumentClassifier(CATALOG)
        result = model.classify(
            "contrato_arrendamiento_local.pdf",
            "Contrato de arrendamiento, póliza y acta de liquidación del inmueble.",
        )
        self.assertEqual(result[0]["code"], "1004.13.31")
        self.assertGreater(result[0]["score"], result[1]["score"])

    def test_dependency_filter_is_respected(self):
        model = DocumentClassifier(CATALOG)
        result = model.search("contrato", dependency_code="1006", top_k=5)
        self.assertEqual([item["dependency_code"] for item in result], ["1006"])

    def test_exact_code_gets_a_boost(self):
        model = DocumentClassifier(CATALOG)
        result = model.classify("documento_3006.11.pdf", "Archivo mensual")
        self.assertEqual(result[0]["code"], "3006.11")


if __name__ == "__main__":
    unittest.main()


class ClinicalArchiveClassificationTests(unittest.TestCase):
    def test_acta_title_outweighs_incidental_trd_mention(self):
        catalog = [
            {
                "code": "3002.2.2.3",
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_code": "2",
                "series_name": "ACTAS",
                "subseries_code": "3",
                "subseries_name": "Actas Comité de Archivo",
                "document_types": ["Acta de comité de Archivo"],
                "procedure": "Decisiones administrativas y técnicas de archivo.",
            },
            {
                "code": "3002.2.2.7",
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_code": "2",
                "series_name": "ACTAS",
                "subseries_code": "7",
                "subseries_name": "Actas Comité de Historias Clínicas",
                "document_types": ["Acta de comité de Historias Clínicas"],
                "procedure": "Seguimiento al diligenciamiento y manejo de historias clínicas.",
            },
            {
                "code": "3002.2.29.381",
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_code": "29",
                "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
                "subseries_code": "381",
                "subseries_name": "Tablas de Retención Documental",
                "document_types": ["Acta de socialización de tabla de retención documental"],
                "procedure": "Instrumento para administrar la producción documental.",
            },
        ]
        model = DocumentClassifier(catalog)
        text = """=== PÁGINA 1 ===
ACTA DE COMITÉ DE ARCHIVO CLÍNICO
ACTA No. 012
Se revisan las historias clínicas, su custodia, préstamos y compromisos.
=== PÁGINA 2 ===
El comité analiza casos clínicos y decisiones de conservación.
=== PÁGINA 3 ===
En un punto secundario se autoriza actualizar la tabla de retención documental.
"""
        result = model.classify(
            "ACTA_COMITE_ARCHIVO_CLINICO.pdf",
            text,
            dependency_code="3002.2",
            top_k=3,
        )
        self.assertEqual(result[0]["code"], "3002.2.2.7")
        self.assertNotEqual(result[0]["code"], "3002.2.29.381")
        self.assertGreater(result[0]["probability"], result[1]["probability"])
        self.assertIn("model_version", result[0])
        self.assertTrue(result[0]["evidence"])


    def test_prestamo_historia_clinica_title_is_not_confused_with_pruebas(self):
        catalog = [
            {
                "code": "3002.2.30.246",
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_name": "INSTRUMENTOS DE CONTROL",
                "subseries_name": "Instrumentos de Control de Registro de Prestamo de Historias Clínicas",
                "document_types": ["Registro de préstamo de historias clínicas"],
                "procedure": "Control de entrega, préstamo y devolución de historias clínicas.",
            },
            {
                "code": "2001.1.30.276",
                "dependency_code": "2001.1",
                "dependency_name": "LABORATORIO",
                "series_name": "INSTRUMENTOS DE CONTROL",
                "subseries_name": "Instrumentos de Control de Reporte de Resultados Pruebas Rápidas",
                "document_types": ["Reporte de resultados de pruebas clínicas"],
                "procedure": "Resultados de pruebas rápidas de laboratorio.",
            },
            {
                "code": "3002.2.30.234",
                "dependency_code": "3002.2",
                "dependency_name": "GESTIÓN DOCUMENTAL",
                "series_name": "INSTRUMENTOS DE CONTROL",
                "subseries_name": "Instrumentos de Control de Registro de Documentos Entregados a Historias Clínicas",
                "document_types": ["Registro de entrega"],
                "procedure": "Entrega de documentos al archivo clínico.",
            },
        ]
        model = DocumentClassifier(catalog)
        text = """=== PÁGINA 1 ===
PRÉSTAMO DE HISTORIAS CLÍNICAS
Registro del préstamo, fecha de entrega, responsable y devolución de la historia clínica.
=== PÁGINA 2 ===
El formato incluye una referencia secundaria a pruebas clínicas realizadas al paciente.
"""
        result = model.classify("formato_control_246.pdf", text, top_k=3)
        self.assertEqual(result[0]["code"], "3002.2.30.246")
        self.assertGreater(result[0]["probability"], result[1]["probability"])
        self.assertIn("Préstamo identificado en el título", result[0]["evidence"])
        self.assertIn("Título específico: préstamo de historias clínicas", result[0]["evidence"])

    def test_probabilities_are_normalized_for_candidate_pool(self):
        model = DocumentClassifier(CATALOG)
        result = model.classify("contrato.pdf", "Contrato de arrendamiento y póliza.", top_k=3)
        self.assertAlmostEqual(sum(item["probability"] for item in result), 1.0, places=5)
