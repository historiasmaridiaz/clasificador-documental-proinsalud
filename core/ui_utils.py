from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd


def preview_widget_key(classification_id: int | str, position: int, sha256: str = "") -> str:
    """Genera una clave estable y única aunque el mismo documento se cargue varias veces."""

    digest = (sha256 or "sin_hash")[:12]
    return f"preview_{classification_id}_{position}_{digest}"


def pdf_page_count(path: str | Path) -> int:
    import fitz

    with fitz.open(str(path)) as document:
        return int(document.page_count)


def render_pdf_page(path: str | Path, page_number: int = 1, zoom: float = 1.6) -> bytes:
    """Renderiza una página PDF como PNG, evitando la dependencia opcional de st.pdf."""

    import fitz

    with fitz.open(str(path)) as document:
        if document.page_count < 1:
            raise ValueError("El PDF no contiene páginas.")
        index = max(0, min(int(page_number) - 1, document.page_count - 1))
        page = document.load_page(index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
        return pixmap.tobytes("png")


def merge_results_by_sha(existing: list[dict], new_results: list[dict]) -> list[dict]:
    """Acumula lotes en pantalla y reemplaza una repetición del mismo archivo."""

    merged = list(existing)
    position_by_hash = {
        str(item.get("sha256", "")): index
        for index, item in enumerate(merged)
        if item.get("sha256")
    }
    for result in new_results:
        digest = str(result.get("sha256", ""))
        existing_position = position_by_hash.get(digest) if digest else None
        if existing_position is None:
            if digest:
                position_by_hash[digest] = len(merged)
            merged.append(result)
        else:
            merged[existing_position] = result
    return merged


def ordered_archival_options(
    official_values: Iterable[Any],
    other_label: str,
    *,
    include_no_apply: bool = False,
) -> list[str]:
    """Ordena opciones de revisión: OTROS primero y después solo la TRD activa.

    Los términos BANTER no se mezclan aquí; se consultan desde su flujo dedicado.
    """

    normalized: dict[str, str] = {}
    for value in official_values:
        label = str(value or "").strip()
        if not label or label in {other_label, "No aplica"}:
            continue
        normalized.setdefault(label.casefold(), label)
    ordered = [other_label]
    if include_no_apply:
        ordered.append("No aplica")
    ordered.extend(sorted(normalized.values(), key=lambda value: value.casefold()))
    return ordered



def series_options_for_dependency(
    entries: Iterable[dict[str, Any]],
    dependency_code: str,
    other_label: str,
) -> list[str]:
    """Devuelve únicamente las series oficiales de una dependencia, con OTROS primero."""

    dep = str(dependency_code or "").strip()
    values = (
        entry.get("series_name")
        for entry in entries
        if not dep or str(entry.get("dependency_code") or "").strip() == dep
    )
    return ordered_archival_options(values, other_label)


def subseries_options_for_series(
    entries: Iterable[dict[str, Any]],
    dependency_code: str,
    series_name: str,
    other_label: str,
    *,
    include_no_apply: bool = True,
) -> list[str]:
    """Devuelve solo las subseries oficiales de la serie elegida dentro de la dependencia."""

    dep = str(dependency_code or "").strip()
    series = str(series_name or "").strip()
    values = (
        entry.get("subseries_name")
        for entry in entries
        if (not dep or str(entry.get("dependency_code") or "").strip() == dep)
        and (not series or str(entry.get("series_name") or "").strip() == series)
    )
    return ordered_archival_options(values, other_label, include_no_apply=include_no_apply)

def merge_editor_subset(
    base: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    id_column: str = "id",
) -> pd.DataFrame:
    """Reintegra una tabla con columnas ocultas sin perder sus valores originales."""

    merged = base.copy()
    if merged.empty or edited.empty or id_column not in merged.columns or id_column not in edited.columns:
        return merged
    editable_columns = [column for column in edited.columns if column != id_column and column in merged.columns]
    if not editable_columns:
        return merged
    edited_by_id = edited.set_index(id_column, drop=False)
    for index, row in merged.iterrows():
        row_id = row[id_column]
        if row_id not in edited_by_id.index:
            continue
        edited_row = edited_by_id.loc[row_id]
        if isinstance(edited_row, pd.DataFrame):
            edited_row = edited_row.iloc[0]
        for column in editable_columns:
            merged.at[index, column] = edited_row[column]
    return merged

def preferred_dependency_code(
    records: Iterable[dict[str, Any]],
    catalog_dependency_codes: Iterable[str],
    current: str = "",
) -> str:
    """Elige una dependencia de trabajo útil sin bloquear los desplegables.

    Conserva la selección actual cuando sigue siendo válida. En una apertura nueva
    prioriza la primera dependencia que realmente tenga documentos visibles y, si
    todavía no hay una inferencia de dependencia, usa la primera del catálogo.
    """

    catalog_order = [str(code or "").strip() for code in catalog_dependency_codes if str(code or "").strip()]
    current_value = str(current or "").strip()
    if current_value in catalog_order:
        return current_value
    present = {
        str(record.get("dependency_code") or "").strip()
        for record in records
        if str(record.get("dependency_code") or "").strip()
    }
    for code in catalog_order:
        if code in present:
            return code
    return catalog_order[0] if catalog_order else ""


def set_boolean_column(frame: pd.DataFrame, column: str, value: bool) -> pd.DataFrame:
    """Devuelve una copia con toda una columna booleana marcada o desmarcada."""

    updated = frame.copy()
    if column not in updated.columns:
        updated[column] = bool(value)
    else:
        updated.loc[:, column] = bool(value)
    return updated

