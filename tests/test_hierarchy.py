import unittest

from core.hierarchy import canonicalize_custom_entry, official_equivalent


ENTRIES = [
    {
        "code": "3002.2.29.336",
        "dependency_code": "3002.2",
        "dependency_name": "GESTIÓN DOCUMENTAL",
        "series_code": "29",
        "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
        "subseries_code": "336",
        "subseries_name": "Inventarios Documentales de Archivo Central",
        "document_types": ["Inventario documental"],
    },
    {
        "code": "3002.2.29.381",
        "dependency_code": "3002.2",
        "dependency_name": "GESTIÓN DOCUMENTAL",
        "series_code": "29",
        "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
        "subseries_code": "381",
        "subseries_name": "Tablas de Retención Documental",
        "document_types": ["Tabla de retención documental"],
    },
]


class HierarchyCanonicalizationTests(unittest.TestCase):
    def test_uncoded_banter_series_reuses_official_series_code(self):
        result = official_equivalent(
            ENTRIES,
            "3002.2",
            "Instrumentos Archivísticos",
            "",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "3002.2.29")
        self.assertEqual(result["canonical_match"], "series")
        self.assertFalse(result["is_other"])

    def test_exact_uncoded_subseries_reuses_full_official_code(self):
        custom = {
            "is_other": True,
            "is_banter": True,
            "dependency_code": "3002.2",
            "dependency_name": "GESTIÓN DOCUMENTAL",
            "series_name": "INSTRUMENTOS ARCHIVÍSTICOS",
            "subseries_name": "Tablas de Retención Documental",
        }
        result = canonicalize_custom_entry(custom, ENTRIES)
        self.assertEqual(result["code"], "3002.2.29.381")
        self.assertEqual(result["canonical_match"], "subseries")
        self.assertFalse(result["is_other"])


if __name__ == "__main__":
    unittest.main()
