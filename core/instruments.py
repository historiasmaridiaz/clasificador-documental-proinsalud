from __future__ import annotations

import io
import json
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from openpyxl.styles import Font, PatternFill

TABLE_SOURCE_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}


def _clean_basename(value: str, fallback: str = "instrumento") -> str:
    raw = Path(str(value).replace("\\", "/")).name
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(char)
    )
    normalized = re.sub(r"[^A-Za-z0-9._ -]+", "_", normalized).strip(" ._")
    if not normalized:
        normalized = fallback
    extension = Path(normalized).suffix.lower()
    if extension not in TABLE_SOURCE_EXTENSIONS:
        extension = ".xlsx"
    stem = Path(normalized).stem[:120].rstrip(" ._") or fallback
    return f"{stem}{extension}"


def persist_catalog_sources(
    root_dir: str | Path,
    catalog_id: int,
    source_files: Iterable[dict[str, Any] | tuple[str, bytes]],
) -> list[dict[str, str]]:
    """Guarda las tablas originales de una versión en una ruta corta y trazable."""

    destination = Path(root_dir) / str(int(catalog_id))
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, str]] = []
    used_names: set[str] = set()
    for index, item in enumerate(source_files, start=1):
        if isinstance(item, tuple):
            original_name, data = str(item[0]), bytes(item[1])
        else:
            original_name, data = str(item.get("name", "instrumento.xlsx")), bytes(item.get("data", b""))
        if not data:
            continue
        extension = Path(original_name.replace("\\", "/")).suffix.lower()
        if extension not in TABLE_SOURCE_EXTENSIONS:
            continue
        stored_name = _clean_basename(original_name)
        if stored_name.casefold() in used_names:
            stored_name = f"{index:03d}_{stored_name}"
        used_names.add(stored_name.casefold())
        (destination / stored_name).write_bytes(data)
        manifest.append({"original_name": original_name, "stored_name": stored_name})

    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def load_catalog_sources(
    root_dir: str | Path,
    catalog_id: int,
    fallback_zip: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Carga los Excel/CSV de la versión activa; usa el paquete institucional como respaldo."""

    directory = Path(root_dir) / str(int(catalog_id))
    manifest_path = directory / "manifest.json"
    records: list[dict[str, Any]] = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = []
        for item in manifest:
            path = directory / str(item.get("stored_name", ""))
            if path.is_file() and path.suffix.lower() in TABLE_SOURCE_EXTENSIONS:
                records.append(
                    {
                        "name": str(item.get("original_name") or path.name),
                        "stored_name": path.name,
                        "data": path.read_bytes(),
                        "path": str(path),
                    }
                )
        if records:
            return records

    fallback = Path(fallback_zip) if fallback_zip else None
    if fallback and fallback.is_file():
        with zipfile.ZipFile(fallback) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                extension = Path(member.filename).suffix.lower()
                if extension not in TABLE_SOURCE_EXTENSIONS:
                    continue
                records.append(
                    {
                        "name": member.filename,
                        "stored_name": Path(member.filename).name,
                        "data": archive.read(member),
                        "path": "",
                    }
                )
    return records


def source_bundle_bytes(records: Iterable[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, record in enumerate(records, start=1):
            name = _clean_basename(str(record.get("name", "instrumento.xlsx")))
            if name.casefold() in used:
                name = f"{index:03d}_{name}"
            used.add(name.casefold())
            archive.writestr(name, bytes(record.get("data", b"")))
    return buffer.getvalue()


def _normalized(value: str) -> str:
    text = "".join(
        char for char in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(char)
    ).upper()
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def find_trd_source(records: Iterable[dict[str, Any]], dependency_code: str, dependency_name: str = "") -> dict[str, Any] | None:
    code = str(dependency_code).strip()
    normalized_name = _normalized(dependency_name)
    candidates = []
    for record in records:
        filename = Path(str(record.get("name", "")).replace("\\", "/")).name
        normalized_filename = _normalized(filename)
        if " TRD " not in f" {normalized_filename} ":
            continue
        score = 0
        if code and filename.upper().startswith(f"{code.upper()} TRD"):
            score += 10
        if code and _normalized(code) in normalized_filename:
            score += 5
        if normalized_name and normalized_name in normalized_filename:
            score += 4
        candidates.append((score, filename.casefold(), record))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def find_ccd_source(records: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if "CCD" in _normalized(Path(str(record.get("name", ""))).name):
            return record
    return None



def preferred_sheet_index(
    sheet_names: Iterable[str],
    dependency_code: str = "",
    dependency_name: str = "",
) -> int:
    """Selecciona por defecto la hoja que mejor coincide con la dependencia."""

    names = list(sheet_names)
    if not names:
        return 0
    normalized_code = _normalized(dependency_code)
    normalized_name = _normalized(dependency_name)
    scored: list[tuple[int, int]] = []
    for index, sheet in enumerate(names):
        normalized_sheet = _normalized(sheet)
        score = 0
        if normalized_name and normalized_name in normalized_sheet:
            score += 20
        if normalized_code and normalized_code in normalized_sheet:
            score += 8
        if "TRD" in normalized_sheet:
            score += 1
        scored.append((score, index))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]

def workbook_sheet_names(name: str, data: bytes) -> list[str]:
    extension = Path(str(name)).suffix.lower()
    if extension in {".csv", ".tsv"}:
        return ["Datos"]
    with pd.ExcelFile(io.BytesIO(data)) as workbook:
        return list(workbook.sheet_names)


def read_source_sheet(name: str, data: bytes, sheet_name: str | int = 0) -> pd.DataFrame:
    extension = Path(str(name)).suffix.lower()
    if extension in {".csv", ".tsv"}:
        separator = "\t" if extension == ".tsv" else ","
        frame = pd.read_csv(io.BytesIO(data), sep=separator, header=None, dtype=object)
    else:
        frame = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name, header=None, dtype=object)

    def display_value(value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    return frame.apply(lambda column: column.map(display_value))


def dataframe_to_xlsx_bytes(frame: pd.DataFrame, sheet_name: str = "Tabla") -> bytes:
    safe_sheet = re.sub(r"[\\/*?:\[\]]+", " ", str(sheet_name)).strip()[:31] or "Tabla"
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=safe_sheet)
        worksheet = writer.book[safe_sheet]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.font = Font(name=cell.font.name or "Calibri", size=cell.font.sz or 11, bold=True, color="FFFFFF")
            cell.fill = PatternFill(fill_type="solid", fgColor="173F67")
        for column_cells in worksheet.columns:
            values = [str(cell.value or "") for cell in column_cells[:150]]
            width = min(55, max(12, max((len(value) for value in values), default=10) + 2))
            worksheet.column_dimensions[column_cells[0].column_letter].width = width
    return buffer.getvalue()
