from __future__ import annotations

from pathlib import Path


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
