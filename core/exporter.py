from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


EXPORT_COLUMNS = [
    "anio",
    "archivo",
    "codigo_sugerido",
    "puntaje_similitud",
    "confianza",
    "codigo_final",
    "estado",
    "dependencia",
    "serie",
    "subserie",
    "retencion_gestion",
    "retencion_central",
    "disposicion_final",
    "origen_anio",
    "observaciones",
]


def _catalog_map(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(entry.get("code", "")): entry for entry in entries}


def manifest_rows(records: list[dict[str, Any]], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = _catalog_map(entries)
    rows = []
    for record in records:
        code = record.get("final_code") or record.get("suggested_code") or ""
        entry = catalog.get(str(code), {})
        rows.append(
            {
                "anio": record.get("document_year", ""),
                "archivo": record.get("filename", ""),
                "codigo_sugerido": record.get("suggested_code", ""),
                "puntaje_similitud": round(float(record.get("suggested_score", 0)) * 100, 1),
                "confianza": record.get("confidence", ""),
                "codigo_final": code,
                "estado": record.get("status", ""),
                "dependencia": entry.get("dependency_name", ""),
                "serie": entry.get("series_name", ""),
                "subserie": entry.get("subseries_name", ""),
                "retencion_gestion": entry.get("retention_management", ""),
                "retencion_central": entry.get("retention_central", ""),
                "disposicion_final": " | ".join(entry.get("final_disposition") or []),
                "origen_anio": record.get("year_source", ""),
                "observaciones": record.get("reviewer_notes", ""),
            }
        )
    return rows


def to_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def to_json_bytes(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")


def to_xlsx_bytes(rows: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Clasificación"
    ws.append(EXPORT_COLUMNS)
    for row in rows:
        ws.append([row.get(column, "") for column in EXPORT_COLUMNS])

    header_fill = PatternFill("solid", fgColor="0F766E")
    for cell in ws[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = [12, 35, 18, 18, 13, 18, 14, 28, 28, 34, 18, 18, 28, 28, 35]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, index).column_letter].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _folder_component(value: Any, fallback: str, max_length: int = 120) -> str:
    text = unicodedata.normalize("NFC", str(value or fallback))
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1F]+", "_", text).strip(" ._")
    return text[:max_length].rstrip(" ._") or fallback


def _file_component(value: Any, fallback: str, max_length: int = 100) -> str:
    cleaned = _folder_component(value, fallback, max_length=500)
    suffix = Path(cleaned).suffix
    stem = Path(cleaned).stem
    available = max(12, max_length - len(suffix))
    return f"{stem[:available].rstrip(' ._')}{suffix}" or fallback


def _fit_zip_target(parts: list[str], filename: str, max_length: int = 240) -> tuple[list[str], str]:
    fitted_parts = list(parts)
    fitted_file = filename

    def current_length() -> int:
        return len("/".join(fitted_parts + [fitted_file]))

    if current_length() <= max_length:
        return fitted_parts, fitted_file

    suffix = Path(fitted_file).suffix
    stem = Path(fitted_file).stem
    reduction = min(max(0, len(stem) - 24), current_length() - max_length)
    if reduction:
        fitted_file = f"{stem[: len(stem) - reduction].rstrip(' ._')}{suffix}"

    for index in range(len(fitted_parts) - 1, 0, -1):
        if current_length() <= max_length:
            break
        component = fitted_parts[index]
        reduction = min(max(0, len(component) - 28), current_length() - max_length)
        if reduction:
            fitted_parts[index] = component[: len(component) - reduction].rstrip(" ._")
    return fitted_parts, fitted_file


def _entry_folder_parts(entry: dict[str, Any], year: str) -> list[str]:
    dependency_code = str(entry.get("dependency_code", ""))
    series_code = str(entry.get("series_code", ""))
    code = str(entry.get("code", ""))
    parts = [
        _folder_component(year, "SIN_ANIO", max_length=12),
        _folder_component(
            f"{dependency_code} - {entry.get('dependency_name', '')}",
            "DEPENDENCIA",
            max_length=75,
        ),
        _folder_component(
            f"{dependency_code}.{series_code} - {entry.get('series_name', '')}",
            "SERIE",
            max_length=85,
        ),
    ]
    if entry.get("subseries_code"):
        parts.append(
            _folder_component(
                f"{code} - {entry.get('subseries_name', '')}",
                code or "SUBSERIE",
                max_length=95,
            )
        )
    return parts


def to_pdf_bytes(rows: list[dict[str, Any]], title: str = "Tabla de clasificación documental") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    page_size = landscape(A4)
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=17 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="Clasificador documental TRD/CCD",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0F5F59"),
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )
    body_style = ParagraphStyle(
        "Cell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor("#1F2933"),
    )
    header_style = ParagraphStyle(
        "HeaderCell",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    def paragraph(value: Any, style: ParagraphStyle = body_style) -> Paragraph:
        text = str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(text, style)

    headers = ["Año", "Archivo", "Código final", "Estado", "Dependencia", "Serie / Subserie", "Similitud"]
    table_data = [[paragraph(value, header_style) for value in headers]]
    for row in rows:
        series = str(row.get("serie", ""))
        if row.get("subserie"):
            series = f"{series} / {row.get('subserie')}"
        table_data.append(
            [
                paragraph(row.get("anio")),
                paragraph(row.get("archivo")),
                paragraph(row.get("codigo_final")),
                paragraph(row.get("estado")),
                paragraph(row.get("dependencia")),
                paragraph(series),
                paragraph(f"{row.get('puntaje_similitud', 0)}%"),
            ]
        )

    table = Table(
        table_data,
        colWidths=[13 * mm, 54 * mm, 25 * mm, 23 * mm, 39 * mm, 90 * mm, 20 * mm],
        repeatRows=1,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (3, -1), "CENTER"),
                ("ALIGN", (6, 1), (6, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C7C5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF7F5")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def draw_page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#0F766E"))
        canvas.setLineWidth(0.7)
        canvas.line(10 * mm, page_size[1] - 10 * mm, page_size[0] - 10 * mm, page_size[1] - 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#52606D"))
        canvas.drawString(10 * mm, 7 * mm, f"Generado: {generated}")
        canvas.drawRightString(page_size[0] - 10 * mm, 7 * mm, f"Página {doc.page}")
        canvas.restoreState()

    story = [Paragraph(title, title_style), Paragraph(f"Registros incluidos: {len(rows)}", body_style), Spacer(1, 3 * mm), table]
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


def build_classified_zip(
    records: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    include_full_structure: bool = False,
    years: list[str] | None = None,
    dependency_codes: list[str] | None = None,
) -> bytes:
    catalog = _catalog_map(entries)
    rows = manifest_rows(records, entries)
    buffer = io.BytesIO()
    used_paths: set[str] = set()
    missing_files: list[str] = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("MANIFIESTO_CLASIFICACION.csv", to_csv_bytes(rows))
        archive.writestr("MANIFIESTO_CLASIFICACION.json", to_json_bytes(rows))
        archive.writestr("TABLA_CLASIFICACION.pdf", to_pdf_bytes(rows))
        if include_full_structure:
            selected_years = years or sorted({str(r.get("document_year") or "SIN_ANIO") for r in records})
            selected_dependencies = set(dependency_codes or [])
            directory_paths: set[str] = set()
            for year in selected_years:
                for entry in entries:
                    if selected_dependencies and str(entry.get("dependency_code")) not in selected_dependencies:
                        continue
                    directory_parts, _ = _fit_zip_target(_entry_folder_parts(entry, year), "", max_length=220)
                    directory_paths.add("/".join(directory_parts) + "/")
            for directory in sorted(directory_paths):
                archive.writestr(directory, b"")
        for record in records:
            source = Path(str(record.get("stored_path", "")))
            if not source.is_file():
                missing_files.append(str(record.get("filename", source.name)))
                continue
            code = str(record.get("final_code") or record.get("suggested_code") or "")
            entry = catalog.get(code, {})
            year = str(record.get("document_year") or "SIN_ANIO")
            if record.get("status") == "Descartada":
                parts = [_folder_component(year, "SIN_ANIO"), "DESCARTADOS"]
            elif entry:
                parts = _entry_folder_parts(entry, year)
            else:
                parts = [_folder_component(year, "SIN_ANIO"), "SIN_CLASIFICACION"]
            filename = _file_component(Path(str(record.get("filename", source.name))).name, source.name)
            parts, filename = _fit_zip_target(parts, filename)
            target = "/".join(parts + [filename])
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            counter = 2
            while target in used_paths:
                target = "/".join(parts + [f"{stem}_{counter}{suffix}"])
                counter += 1
            used_paths.add(target)
            archive.write(source, target)
        if missing_files:
            archive.writestr(
                "ERRORES_EXPORTACION.txt",
                "No se encontraron los archivos originales de los siguientes registros:\n"
                + "\n".join(f"- {name}" for name in missing_files),
            )
    return buffer.getvalue()
