import unittest
from pathlib import Path

from core.banter import BanterSearchEngine, load_banter_reference, to_custom_classification


class BanterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "data" / "banter_agn_referencia.json"
        cls.metadata, cls.terms = load_banter_reference(path)
        cls.engine = BanterSearchEngine(cls.terms)

    def test_local_reference_is_loaded(self):
        self.assertGreaterEqual(len(self.terms), 100)
        self.assertEqual(self.metadata.get("source_version"), "2.1")

    def test_temperature_query_returns_control_term(self):
        matches = self.engine.search(
            "registro diario de temperatura y humedad relativa del archivo central",
            top_k=8,
        )
        combined = " ".join(
            f"{item.get('series_name', '')} {item.get('subseries_name', '')}" for item in matches[:5]
        ).lower()
        self.assertIn("temperatura", combined)
        self.assertIn("humedad", combined)

    def test_banter_assignment_has_no_official_code(self):
        term = self.terms[0]
        custom = to_custom_classification(term, "3002.2", "GESTIÓN DOCUMENTAL")
        self.assertTrue(custom["is_banter"])
        self.assertEqual(custom["code"], "")
        self.assertEqual(custom["dependency_code"], "3002.2")


if __name__ == "__main__":
    unittest.main()
