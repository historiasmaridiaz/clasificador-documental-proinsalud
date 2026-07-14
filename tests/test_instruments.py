from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

from core.instruments import (
    dataframe_to_xlsx_bytes,
    find_ccd_source,
    find_trd_source,
    load_catalog_sources,
    persist_catalog_sources,
    preferred_sheet_index,
    read_source_sheet,
    source_bundle_bytes,
    workbook_sheet_names,
)


class InstrumentSourceTests(unittest.TestCase):
    @staticmethod
    def workbook_bytes(title: str) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame([[title, "VALOR"], ["SERIE", "ACTAS"]]).to_excel(
                writer, index=False, header=False, sheet_name="TRD"
            )
        return buffer.getvalue()

    def test_sources_are_persisted_and_recovered_by_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trd = self.workbook_bytes("TABLA DE RETENCIÓN DOCUMENTAL")
            ccd = self.workbook_bytes("CUADRO DE CLASIFICACIÓN DOCUMENTAL")
            persist_catalog_sources(
                tmp,
                7,
                [
                    {"name": "3002.2 TRD GESTION DOCUMENTAL.xlsx", "data": trd},
                    {"name": "CCD PROINSALUD.xlsx", "data": ccd},
                ],
            )
            records = load_catalog_sources(tmp, 7)
            self.assertEqual(len(records), 2)
            self.assertEqual(
                find_trd_source(records, "3002.2", "GESTIÓN DOCUMENTAL")["name"],
                "3002.2 TRD GESTION DOCUMENTAL.xlsx",
            )
            self.assertEqual(find_ccd_source(records)["name"], "CCD PROINSALUD.xlsx")

    def test_original_excel_can_be_previewed_and_downloaded(self) -> None:
        data = self.workbook_bytes("TABLA DE RETENCIÓN DOCUMENTAL")
        self.assertEqual(workbook_sheet_names("tabla.xlsx", data), ["TRD"])
        frame = read_source_sheet("tabla.xlsx", data, "TRD")
        self.assertEqual(frame.iloc[0, 0], "TABLA DE RETENCIÓN DOCUMENTAL")
        normalized = dataframe_to_xlsx_bytes(pd.DataFrame([{"Código": "3002.2.2", "Serie": "ACTAS"}]), "TRD")
        self.assertTrue(normalized.startswith(b"PK"))

    def test_preferred_sheet_matches_selected_dependency(self) -> None:
        sheets = [
            "TRD SUBGERENCIA ADM Y FIN.",
            "TRD COMPRAS",
            "TRD GESTION DOCUMENTAL",
        ]
        self.assertEqual(
            preferred_sheet_index(sheets, "3002.2", "GESTIÓN DOCUMENTAL"),
            2,
        )

    def test_bundle_contains_each_original_table_once(self) -> None:
        records = [
            {"name": "3002.2 TRD GESTION DOCUMENTAL.xlsx", "data": b"uno"},
            {"name": "CCD PROINSALUD.xlsx", "data": b"dos"},
        ]
        payload = source_bundle_bytes(records)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(sorted(archive.namelist()), sorted([r["name"] for r in records]))

    def test_fallback_zip_is_used_when_version_has_no_persisted_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "fuentes.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("1000 TRD GERENCIA.xlsx", self.workbook_bytes("TRD"))
                archive.writestr("ignorar.pdf", b"pdf")
            records = load_catalog_sources(Path(tmp) / "catalogos", 1, archive_path)
            self.assertEqual([record["name"] for record in records], ["1000 TRD GERENCIA.xlsx"])


if __name__ == "__main__":
    unittest.main()
