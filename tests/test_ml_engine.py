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
