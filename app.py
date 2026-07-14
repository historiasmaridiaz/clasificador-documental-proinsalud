from __future__ import annotations

import hashlib
import hmac
import json
import os

# Evita sobrecarga de hilos BLAS/SVD al construir el índice semántico local.
# En algunos equipos Windows la detección automática crea demasiados hilos y
# hace que el inicio parezca detenido durante varios minutos.
for _thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_variable, "1")

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core.banter import BANTER_SOURCE_URL, BanterSearchEngine, load_banter_reference, to_custom_classification
from core.catalog import build_catalog_from_files, expand_table_uploads, load_catalog_json
from core.database import Database
from core.exporter import (
    build_classified_zip,
    manifest_rows,
    to_csv_bytes,
    to_json_bytes,
    to_pdf_bytes,
    to_xlsx_bytes,
)
from core.hierarchy import canonicalize_custom_entry, normalize_archival_label, official_equivalent
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
from core.ml_engine import MODEL_VERSION, DocumentClassifier
from core.text_extract import detect_document_year, expand_document_uploads, extract_document, tesseract_status
from core.ui_theme import build_theme_css
from core.ui_utils import (
    merge_editor_subset,
    merge_results_by_sha,
    preferred_dependency_code,
    set_boolean_column,
    ordered_archival_options,
    series_options_for_dependency,
    subseries_options_for_series,
    pdf_page_count,
    preview_widget_key,
    render_pdf_page,
)


PROJECT_DIR = Path(__file__).resolve().parent
APP_VERSION = "2026.07.13-TRD-INSTRUMENTS-SCOPE-9"

DEFAULT_CATALOG = PROJECT_DIR / "data" / "catalogo_proinsalud.json"
ORGANIGRAM_PATH = PROJECT_DIR / "data" / "organigrama_proinsalud.pdf"
INSTRUCTIONS_PATH = PROJECT_DIR / "data" / "instructivo_gestion_carpetas_trd.pdf"
MASSIVE_TEMPLATE_PATH = PROJECT_DIR / "data" / "plantilla_carpetas_masivas.zip"
SOURCE_TRD_PATH = PROJECT_DIR / "data" / "fuentes_trd_proinsalud.zip"
BANTER_PATH = PROJECT_DIR / "data" / "banter_agn_referencia.json"
RUNTIME_DIR = Path(os.environ.get("CLASIFICADOR_DATA_DIR", PROJECT_DIR / "runtime"))
CATALOG_SOURCE_DIR = RUNTIME_DIR / "catalog_sources"
DOCUMENT_UPLOAD_TYPES = [
    "pdf", "docx", "xlsx", "xlsm", "xls", "pptx", "odt", "eml", "txt", "md", "csv", "tsv",
    "json", "xml", "html", "htm", "rtf", "log", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "zip",
]
OTHER_PREFIX = "__OTHER__::"
GENERAL_OTHER_KEY = "__OTHER__::GENERAL"
OTHER_SERIES_LABEL = "OTROS / OTRAS SERIES — sin código TRD"
OTHER_SUBSERIES_LABEL = "OTROS / OTRAS SUBSERIES — sin código TRD"
CURRENT_YEAR = datetime.now().year


st.set_page_config(
    page_title="Gestión documental inteligente — PROINSALUD",
    layout="wide",
    initial_sidebar_state="expanded",
)


def configured_app_password() -> str:
    password = os.environ.get("APP_PASSWORD", "")
    if password:
        return password
    try:
        return str(st.secrets.get("APP_PASSWORD", ""))
    except Exception:
        return ""


def configured_admin_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD", "")
    if password:
        return password
    try:
        secret = str(st.secrets.get("ADMIN_PASSWORD", ""))
        if secret:
            return secret
    except Exception:
        pass
    return "archivo123"


def require_optional_app_password() -> None:
    expected = configured_app_password()
    if not expected or st.session_state.get("app_access_authorized"):
        return
    st.title("Acceso al clasificador documental")
    supplied = st.text_input("Contraseña general", type="password", key="app_access_password")
    if supplied:
        if hmac.compare_digest(supplied, expected):
            st.session_state["app_access_authorized"] = True
            st.rerun()
        st.error("Contraseña incorrecta.")
    st.stop()


require_optional_app_password()

if "dark_mode_v5" not in st.session_state:
    st.session_state["dark_mode_v5"] = False
if "review_focus_mode_v5" not in st.session_state:
    st.session_state["review_focus_mode_v5"] = False

css = build_theme_css(
    dark_mode=bool(st.session_state.get("dark_mode_v5")),
    focus_mode=bool(st.session_state.get("review_focus_mode_v5")),
)
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def get_database(path: str) -> Database:
    return Database(path)


@st.cache_resource(show_spinner=False)
def get_classifier(entries_json: str, examples_json: str) -> DocumentClassifier:
    return DocumentClassifier(json.loads(entries_json), json.loads(examples_json))


@st.cache_resource(show_spinner=False)
def get_banter_engine(terms_json: str) -> BanterSearchEngine:
    return BanterSearchEngine(json.loads(terms_json))


def initialize() -> tuple[Database, dict[str, Any], DocumentClassifier]:
    db = get_database(str(RUNTIME_DIR))
    if DEFAULT_CATALOG.exists():
        default_entries = load_catalog_json(DEFAULT_CATALOG)
        db.seed_catalog(
            "PROINSALUD — TRD/CCD institucional",
            default_entries,
            {"origen": DEFAULT_CATALOG.name, "registros": len(default_entries)},
        )
    catalog = db.active_catalog()
    classifier = get_classifier(
        json.dumps(catalog["entries"], ensure_ascii=False, sort_keys=True),
        json.dumps(db.learned_examples(), ensure_ascii=False, sort_keys=True),
    )
    return db, catalog, classifier


def navigate_to(page_name: str) -> None:
    st.session_state["main_navigation"] = page_name


def dependency_options(entries: list[dict[str, Any]]) -> list[tuple[str, str]]:
    values = {
        (str(entry.get("dependency_code", "")), str(entry.get("dependency_name", "")))
        for entry in entries
        if entry.get("dependency_code")
    }

    def sort_key(item: tuple[str, str]) -> tuple[Any, ...]:
        parts = []
        for part in item[0].split("."):
            parts.append(int(part) if part.isdigit() else part)
        return tuple(parts)

    return sorted(values, key=sort_key)


def entry_table(rows: list[dict[str, Any]], include_score: bool = False) -> pd.DataFrame:
    data = []
    for entry in rows:
        item = {
            "Código": entry.get("code") or "Sin código",
            "Fuente": entry.get("source") or ("TRD PROINSALUD" if entry.get("code") else "OTROS / revisión"),
            "Dependencia": entry.get("dependency_name", ""),
            "Serie": entry.get("series_name", ""),
            "Subserie": entry.get("subseries_name", "") or "No aplica",
            "Tipos documentales": " • ".join(entry.get("document_types") or []),
            "Retención gestión": entry.get("retention_management", ""),
            "Retención central": entry.get("retention_central", ""),
            "Disposición": " | ".join(entry.get("final_disposition") or []),
        }
        if include_score:
            item = {
                "Probabilidad": entry.get("score_percent", 0),
                "Relevancia": entry.get("relevance_percent", entry.get("score_percent", 0)),
                "Confianza": entry.get("confidence", ""),
                **item,
            }
        data.append(item)
    return pd.DataFrame(data)


def hierarchy_table(rows: list[dict[str, Any]], include_score: bool = False) -> pd.DataFrame:
    data = []
    for entry in rows:
        series_code = ".".join(
            value for value in [str(entry.get("dependency_code", "")), str(entry.get("series_code", ""))] if value
        )
        item = {
            "Código TRD": entry.get("code", ""),
            "Sección": " - ".join(v for v in [str(entry.get("section_code", "")), str(entry.get("section_name", ""))] if v),
            "Dependencia": " - ".join(v for v in [str(entry.get("dependency_code", "")), str(entry.get("dependency_name", ""))] if v),
            "Serie": " - ".join(v for v in [series_code, str(entry.get("series_name", ""))] if v),
            "Subserie": entry.get("subseries_name", "") or "No aplica",
        }
        if include_score:
            item["Probabilidad"] = entry.get("score_percent", 0)
            item["Relevancia"] = entry.get("relevance_percent", entry.get("score_percent", 0))
            item["Confianza"] = entry.get("confidence", "")
        data.append(item)
    return pd.DataFrame(data)


def render_document_preview(record: dict[str, Any], key_prefix: str) -> None:
    path = Path(str(record.get("stored_path", "")))
    extension = str(record.get("extension", "")).lower()
    if path.is_file() and extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        st.image(str(path), caption=record.get("filename", path.name), use_container_width=True)
    elif path.is_file() and extension == ".pdf":
        try:
            pages = pdf_page_count(path)
            page_number = st.number_input(
                "Página",
                min_value=1,
                max_value=max(1, pages),
                value=1,
                step=1,
                key=f"{key_prefix}_pdf_page",
            )
            st.image(
                render_pdf_page(path, int(page_number)),
                caption=f"{record.get('filename', path.name)} · página {int(page_number)} de {pages}",
                use_container_width=True,
            )
            with st.expander("Ver texto extraído"):
                st.text_area(
                    "Texto OCR/PDF",
                    str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
                    height=220,
                    disabled=True,
                    key=f"{key_prefix}_pdf_text",
                    label_visibility="collapsed",
                )
        except Exception as exc:
            st.warning(f"No fue posible renderizar el PDF: {exc}")
            st.text_area(
                "Contenido extraído",
                str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
                height=320,
                disabled=True,
                key=f"{key_prefix}_fallback_text",
                label_visibility="collapsed",
            )
    else:
        st.text_area(
            "Contenido extraído",
            str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
            height=320,
            disabled=True,
            key=f"{key_prefix}_text",
            label_visibility="collapsed",
        )
    if path.is_file():
        st.download_button(
            "Descargar original",
            data=path.read_bytes(),
            file_name=Path(str(record.get("filename", path.name))).name,
            key=f"{key_prefix}_download",
            use_container_width=True,
        )


def standard_option_label(entry: dict[str, Any]) -> str:
    detail = entry.get("subseries_name") or entry.get("series_name") or "Sin denominación"
    code = entry.get("code") or "SIN CÓDIGO"
    return f"{code} · {entry.get('dependency_name', '')} · {detail}"


def other_entry(dependency_code: str = "", dependency_name: str = "") -> dict[str, Any]:
    return {
        "is_other": True,
        "is_banter": False,
        "source": "OTROS / manual",
        "code": "",
        "dependency_code": dependency_code,
        "dependency_name": dependency_name,
        "series_code": "",
        "series_name": OTHER_SERIES_LABEL,
        "subseries_code": "",
        "subseries_name": "",
        "document_types": [],
        "retention_management": "",
        "retention_central": "",
        "final_disposition": [],
        "procedure": "Requiere análisis del responsable de gestión documental antes de incorporar o ajustar la TRD/CCD.",
    }


def build_classification_options(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    key_to_entry: dict[str, dict[str, Any]] = {}
    key_to_label: dict[str, str] = {}
    label_to_key: dict[str, str] = {}
    for entry in entries:
        key = str(entry.get("code", ""))
        if not key:
            continue
        label = standard_option_label(entry)
        key_to_entry[key] = entry
        key_to_label[key] = label
        label_to_key[label] = key
    general = other_entry()
    general_label = "SIN CÓDIGO · Dependencia por definir · OTROS / OTRAS SERIES"
    key_to_entry[GENERAL_OTHER_KEY] = general
    key_to_label[GENERAL_OTHER_KEY] = general_label
    label_to_key[general_label] = GENERAL_OTHER_KEY
    for dep_code, dep_name in dependency_options(entries):
        key = f"{OTHER_PREFIX}{dep_code}"
        entry = other_entry(dep_code, dep_name)
        label = f"SIN CÓDIGO · {dep_code} - {dep_name} · OTROS / OTRAS SERIES"
        key_to_entry[key] = entry
        key_to_label[key] = label
        label_to_key[label] = key
    return key_to_entry, key_to_label, label_to_key


def dependency_label(code: str, name: str = "") -> str:
    if code:
        resolved = name or next((dep_name for dep_code, dep_name in dependency_options(entries) if dep_code == code), "")
        return f"{code} - {resolved}".strip(" -")
    return "Dependencia por definir"


def dependency_code_from_label(label: str) -> str:
    if not label or label == "Dependencia por definir":
        return ""
    return str(label).split(" - ", 1)[0].strip()


def dependency_name_from_code(code: str) -> str:
    return next((name for dep_code, name in dependency_options(entries) if dep_code == code), "")


def entry_source(entry: dict[str, Any]) -> str:
    if entry.get("is_banter") or "BANTER" in str(entry.get("source", "")).upper():
        return "BANTER AGN (orientativo)"
    if entry.get("code") and not entry.get("is_other"):
        return "TRD PROINSALUD"
    return "OTROS / manual"


def suggested_entry(record: dict[str, Any], catalog_by_code: dict[str, dict[str, Any]]) -> dict[str, Any]:
    code = str(record.get("suggested_code") or "")
    if code and code in catalog_by_code:
        return catalog_by_code[code]
    candidates = record.get("candidates") or []
    return dict(candidates[0]) if candidates else {}


def effective_review_entry(record: dict[str, Any]) -> dict[str, Any]:
    custom = record.get("custom_classification") or {}
    if isinstance(custom, dict) and custom:
        return dict(custom)
    code = str(record.get("final_code") or record.get("suggested_code") or "")
    if code and code in catalog_by_code:
        return dict(catalog_by_code[code])
    return suggested_entry(record, catalog_by_code)


def fallback_candidates(
    candidates: list[dict[str, Any]],
    selected_dependency: str = "",
    filename: str = "",
    text: str = "",
) -> list[dict[str, Any]]:
    """Conserva la TRD como primera fuente y envía los casos débiles a OTROS.

    BANTER no se asigna automáticamente: queda como una búsqueda voluntaria dentro
    del editor, después de revisar las opciones oficiales de PROINSALUD.
    """

    if candidates and float(candidates[0].get("score", 0)) >= 0.18:
        return candidates
    dep_code = selected_dependency or (str(candidates[0].get("dependency_code", "")) if candidates else "")
    dep_name = dependency_name_from_code(dep_code)
    fallback = other_entry(dep_code, dep_name)
    fallback.update(
        {
            "score": 0.0,
            "score_percent": 0.0,
            "confidence": "Revisión requerida",
            "needs_review": True,
            "evidence": ["No hubo evidencia suficiente en la TRD activa; revise OTROS o consulte BANTER manualmente."],
        }
    )
    return [fallback, *candidates]

def current_option_key(record: dict[str, Any]) -> str:
    custom = record.get("custom_classification") or {}
    if custom.get("is_other"):
        dep_code = str(custom.get("dependency_code") or "")
        return f"{OTHER_PREFIX}{dep_code}" if dep_code else GENERAL_OTHER_KEY
    code = str(record.get("final_code") or record.get("suggested_code") or "")
    if code:
        return code
    candidates = record.get("candidates") or []
    if candidates and candidates[0].get("is_other"):
        dep_code = str(candidates[0].get("dependency_code") or "")
        return f"{OTHER_PREFIX}{dep_code}" if dep_code else GENERAL_OTHER_KEY
    return GENERAL_OTHER_KEY


def review_rows_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    data = []
    for record in records:
        suggestion = suggested_entry(record, catalog_by_code)
        current = effective_review_entry(record)
        dep_code = str(current.get("dependency_code") or "")
        dep_name = str(current.get("dependency_name") or dependency_name_from_code(dep_code))
        is_other = bool(current.get("is_other")) or not bool(current.get("code"))
        series_name = OTHER_SERIES_LABEL if is_other else str(current.get("series_name") or OTHER_SERIES_LABEL)
        if is_other:
            subseries_name = OTHER_SUBSERIES_LABEL if current.get("subseries_name") else "No aplica"
        else:
            subseries_name = str(current.get("subseries_name") or "No aplica")
        evidence = suggestion.get("evidence") or []
        data.append(
            {
                "id": record["id"],
                "Seleccionar": False,
                "Aprobar": False,
                "Año": int(record.get("document_year") or CURRENT_YEAR),
                "Archivo": record.get("filename", ""),
                "Código": str(current.get("code") or "Sin código"),
                "Fuente": entry_source(current),
                "Predicción IA": standard_option_label(suggestion) if suggestion else "Sin sugerencia",
                "Probabilidad": round(float(record.get("suggested_score", 0)) * 100, 1),
                "Dependencia": dependency_label(dep_code, dep_name),
                "Serie": series_name,
                "Subserie": subseries_name,
                "Estado actual": record.get("status", "Pendiente"),
                "Evidencia": " · ".join(str(value) for value in evidence[:3]),
                "Observaciones": record.get("reviewer_notes", ""),
            }
        )
    return pd.DataFrame(data)


def _find_official_entry(dependency_code: str, series_name: str, subseries_name: str) -> dict[str, Any] | None:
    clean_subseries = "" if subseries_name in {"", "No aplica", OTHER_SUBSERIES_LABEL} else subseries_name
    result = official_equivalent(
        entries,
        dependency_code,
        series_name,
        clean_subseries,
        allow_series_only=not bool(clean_subseries),
    )
    return dict(result) if result else None


def _find_banter_term(series_name: str, subseries_name: str) -> dict[str, Any] | None:
    target_series = normalize_archival_label(series_name)
    target_subseries = normalize_archival_label("" if subseries_name in {"", "No aplica", OTHER_SUBSERIES_LABEL} else subseries_name)
    for term in banter_terms:
        if normalize_archival_label(term.get("series_name", "")) != target_series:
            continue
        if normalize_archival_label(term.get("subseries_name", "")) == target_subseries:
            return dict(term)
    return None


def resolve_hierarchy_selection(
    row: dict[str, Any],
    record: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    dep_code = dependency_code_from_label(str(row.get("Dependencia") or row.get("Dependencia final") or ""))
    dep_name = dependency_name_from_code(dep_code)
    series_name = str(row.get("Serie") or row.get("Serie final") or "").strip()
    subseries_name = str(row.get("Subserie") or row.get("Subserie final") or "").strip()

    if series_name == OTHER_SERIES_LABEL:
        existing = effective_review_entry(record) if record else {}
        if existing.get("is_other") and str(existing.get("dependency_code") or "") == dep_code:
            return dict(existing), ""
        return other_entry(dep_code, dep_name), ""

    official = _find_official_entry(dep_code, series_name, subseries_name)
    if official:
        return official, str(official.get("code", ""))

    # Si la subserie elegida no pertenece a la serie, conserva la serie oficial
    # en lugar de crear una combinación manual inválida o una carpeta duplicada.
    official_series = _find_official_entry(dep_code, series_name, "")
    if official_series:
        return official_series, str(official_series.get("code", ""))

    # La tabla directa contiene únicamente OTROS y términos de la TRD activa.
    # Las denominaciones BANTER se agregan desde el editor detallado, como última opción.
    manual = other_entry(dep_code, dep_name)
    if series_name and series_name != OTHER_SERIES_LABEL:
        manual["series_name"] = series_name
    if subseries_name and subseries_name not in {"No aplica", OTHER_SUBSERIES_LABEL}:
        manual["subseries_name"] = subseries_name
    manual["source"] = "OTROS / manual"
    return manual, ""


def save_review_table(edited: pd.DataFrame, mode: str = "save") -> tuple[int, int]:
    saved = 0
    approved = 0
    records_by_id = {int(record["id"]): record for record in db.list_classifications()}
    for row in edited.to_dict(orient="records"):
        record = records_by_id.get(int(row["id"]))
        if not record:
            continue
        selected_entry, final_code = resolve_hierarchy_selection(row, record)
        selected_entry = canonicalize_custom_entry(
            selected_entry,
            entries,
            filename=str(record.get("filename") or ""),
            extracted_text=str(record.get("extracted_text") or ""),
        )
        final_code = "" if selected_entry.get("is_other") else str(selected_entry.get("code") or final_code)
        should_approve = mode == "all" or (mode == "marked" and bool(row.get("Aprobar")))
        current_status = str(record.get("status") or "Pendiente")
        status = current_status if current_status in {"Aprobada", "Corregida", "Descartada"} else "Pendiente"
        if should_approve:
            original_code = str(record.get("suggested_code") or "")
            status = "Aprobada" if final_code == original_code and not selected_entry.get("is_other") else "Corregida"
            approved += 1
        custom = selected_entry if selected_entry.get("is_other") else {}
        db.update_review(
            int(row["id"]),
            final_code,
            status,
            str(row.get("Observaciones") or ""),
            document_year=int(row["Año"]),
            custom_classification=custom,
        )
        saved += 1
    get_classifier.clear()
    return saved, approved


def save_single_hierarchy(
    record: dict[str, Any],
    selected_entry: dict[str, Any],
    approve: bool,
    notes: str = "",
) -> None:
    selected_entry = canonicalize_custom_entry(
        selected_entry,
        entries,
        filename=str(record.get("filename") or ""),
        extracted_text=str(record.get("extracted_text") or ""),
    )
    final_code = "" if selected_entry.get("is_other") else str(selected_entry.get("code", ""))
    suggested_code = str(record.get("suggested_code") or "")
    if approve:
        status = "Aprobada" if final_code == suggested_code and not selected_entry.get("is_other") else "Corregida"
    else:
        status = "Pendiente"
    db.update_review(
        int(record["id"]),
        final_code,
        status,
        notes or str(record.get("reviewer_notes") or ""),
        document_year=int(record.get("document_year") or CURRENT_YEAR),
        custom_classification=selected_entry if selected_entry.get("is_other") else {},
    )
    get_classifier.clear()


def record_dependency_code(record: dict[str, Any]) -> str:
    custom = record.get("custom_classification") or {}
    if custom.get("dependency_code"):
        return str(custom.get("dependency_code"))
    code = str(record.get("final_code") or record.get("suggested_code") or "")
    if code in catalog_by_code:
        return str(catalog_by_code[code].get("dependency_code", ""))
    suggestion = suggested_entry(record, catalog_by_code)
    return str(suggestion.get("dependency_code", ""))


def record_series_name(record: dict[str, Any]) -> str:
    entry = effective_review_entry(record)
    if entry.get("is_other") or not entry.get("code"):
        return OTHER_SERIES_LABEL
    return str(entry.get("series_name") or "")


REVIEW_DEFAULT_COLUMNS = [
    "Seleccionar",
    "Aprobar",
    "Archivo",
    "Código",
    "Probabilidad",
    "Dependencia",
    "Serie",
    "Subserie",
    "Estado actual",
    "Observaciones",
]


def _review_editor_column_config(
    editor_dependencies: list[str],
    editor_series: list[str],
    editor_subseries: list[str],
) -> dict[str, Any]:
    return {
        "id": None,
        "Seleccionar": st.column_config.CheckboxColumn(
            "Abrir",
            help="Seleccione una fila para abrir su documento y el editor jerárquico.",
            default=False,
            width="small",
        ),
        "Aprobar": st.column_config.CheckboxColumn(
            "Aprobar",
            help="Marque las filas que ya están correctamente clasificadas.",
            default=False,
            width="small",
        ),
        "Año": st.column_config.NumberColumn(
            "Año",
            min_value=1990,
            max_value=CURRENT_YEAR + 1,
            step=1,
            required=True,
        ),
        "Probabilidad": st.column_config.ProgressColumn(
            min_value=0,
            max_value=100,
            format="%.1f%%",
            width="medium",
        ),
        "Dependencia": st.column_config.SelectboxColumn(
            options=editor_dependencies,
            required=True,
            width="large",
        ),
        "Serie": st.column_config.SelectboxColumn(
            options=editor_series,
            required=True,
            width="large",
            help="Primero aparece OTROS; después, únicamente las series de la TRD activa.",
        ),
        "Subserie": st.column_config.SelectboxColumn(
            options=editor_subseries,
            required=True,
            width="large",
            help="Primero aparece OTRAS SUBSERIES; después, únicamente las subseries de la TRD activa.",
        ),
        "Observaciones": st.column_config.TextColumn(width="large"),
    }


def _selected_review_columns(available: list[str]) -> list[str]:
    state_key = "review_visible_columns_v5"
    default = [column for column in REVIEW_DEFAULT_COLUMNS if column in available]
    current = [column for column in st.session_state.get(state_key, default) if column in available]
    if not current:
        current = default
    st.session_state[state_key] = current
    selected = st.multiselect(
        "Mostrar columnas",
        options=available,
        key=state_key,
        help="Puede ocultar información secundaria y dejar visibles solo archivo, serie y subserie.",
    )
    if selected:
        return selected
    return [column for column in ["Archivo", "Serie", "Subserie"] if column in available]


def _set_session_value(key: str, value: Any) -> None:
    st.session_state[key] = value


def _render_selected_document_editor(
    selected_record: dict[str, Any],
    selected_row: dict[str, Any],
    *,
    focused: bool,
) -> None:
    scope = "focus" if focused else "normal"
    selected_from_table, _ = resolve_hierarchy_selection(selected_row, selected_record)
    current = selected_from_table or effective_review_entry(selected_record)
    record_id = int(selected_record["id"])
    mode_key = f"assignment_mode_v6_{scope}_{record_id}"
    valid_modes = ["TRD de PROINSALUD", "Agregar serie manual", "Buscar en BANTER"]
    if st.session_state.get(mode_key) not in valid_modes:
        st.session_state[mode_key] = "TRD de PROINSALUD"

    with st.expander(f"Editar documento · {selected_record['filename']}", expanded=True):
        preview_col, model_col = st.columns([1.05, 1])
        with preview_col:
            render_document_preview(selected_record, f"review_v6_{scope}_{record_id}")
        with model_col:
            st.markdown("**Alternativas de la inteligencia artificial**")
            candidate_rows = selected_record.get("candidates") or []
            st.dataframe(
                entry_table(candidate_rows, include_score=True),
                use_container_width=True,
                hide_index=True,
                height=290,
            )
            top_candidate = candidate_rows[0] if candidate_rows else {}
            if top_candidate.get("evidence"):
                st.caption("Evidencia principal: " + " · ".join(top_candidate.get("evidence") or []))
            metadata = selected_record.get("metadata") or {}
            if metadata.get("pages"):
                st.caption(
                    f"OCR: {metadata.get('ocr_coverage_percent', 0)}% de páginas · "
                    f"modo {metadata.get('ocr_requested_mode', 'no informado')}"
                )
            for warning in selected_record.get("warnings") or []:
                st.warning(warning)

        st.markdown("#### Clasificación final")
        st.caption(
            "Primero use la TRD institucional. Si la opción correcta no existe, elija OTROS y luego agregue una serie o consulte BANTER."
        )
        assignment_mode = st.radio(
            "Origen de la clasificación",
            valid_modes,
            horizontal=True,
            key=mode_key,
            label_visibility="collapsed",
        )

        dep_pairs = dependency_options(entries)
        dep_codes = [code for code, _ in dep_pairs]
        current_dep = str(current.get("dependency_code") or record_dependency_code(selected_record) or "")
        dep_index = dep_codes.index(current_dep) if current_dep in dep_codes else 0

        if assignment_mode == "TRD de PROINSALUD":
            detail_dep = st.selectbox(
                "Dependencia productora",
                options=dep_codes,
                index=dep_index,
                format_func=lambda code: next(f"{c} - {name}" for c, name in dep_pairs if c == code),
                key=f"detail_dep_v6_{scope}_{record_id}",
                help="Al cambiar la dependencia, la lista de series se limita automáticamente a esa dependencia.",
            )
            detail_series_options = series_options_for_dependency(entries, detail_dep, OTHER_SERIES_LABEL)
            current_series = str(current.get("series_name") or "")
            if current.get("is_other") or current_series not in detail_series_options:
                current_series = OTHER_SERIES_LABEL
            series_index = detail_series_options.index(current_series) if current_series in detail_series_options else 0
            detail_series = st.selectbox(
                "Serie",
                options=detail_series_options,
                index=series_index,
                key=f"detail_series_v6_{scope}_{record_id}",
                help="Solo aparecen las series de la dependencia seleccionada; OTROS permanece en primer lugar.",
            )

            if detail_series == OTHER_SERIES_LABEL:
                st.info("La serie no está en la TRD activa. Puede mantenerla como OTROS, agregar una denominación o buscarla en BANTER.")
                other_action_1, other_action_2 = st.columns(2)
                other_action_1.button(
                    "Agregar serie",
                    type="primary",
                    use_container_width=True,
                    key=f"open_manual_v6_{scope}_{record_id}",
                    on_click=_set_session_value,
                    args=(mode_key, "Agregar serie manual"),
                )
                other_action_2.button(
                    "Buscar serie en BANTER",
                    type="primary",
                    use_container_width=True,
                    key=f"open_banter_v6_{scope}_{record_id}",
                    on_click=_set_session_value,
                    args=(mode_key, "Buscar en BANTER"),
                )
                detail_subseries_options = [OTHER_SUBSERIES_LABEL, "No aplica"]
            else:
                detail_subseries_options = subseries_options_for_series(
                    entries,
                    detail_dep,
                    detail_series,
                    OTHER_SUBSERIES_LABEL,
                    include_no_apply=True,
                )

            current_subseries = str(current.get("subseries_name") or "No aplica") or "No aplica"
            if current.get("is_other") or current_subseries not in detail_subseries_options:
                current_subseries = OTHER_SUBSERIES_LABEL if detail_series == OTHER_SERIES_LABEL else "No aplica"
            sub_index = detail_subseries_options.index(current_subseries) if current_subseries in detail_subseries_options else 0
            detail_subseries = st.selectbox(
                "Subserie",
                options=detail_subseries_options,
                index=sub_index,
                key=f"detail_subseries_v6_{scope}_{record_id}",
                help="Solo aparecen las subseries de la serie seleccionada.",
            )

            detail_row = {
                "Dependencia": dependency_label(detail_dep, dependency_name_from_code(detail_dep)),
                "Serie": detail_series,
                "Subserie": detail_subseries,
            }
            selected_assignment, _ = resolve_hierarchy_selection(detail_row, selected_record)
            if selected_assignment.get("is_other"):
                st.caption("Clasificación temporal sin código TRD. Puede guardarla para revisión o usar las opciones anteriores.")
            else:
                st.info(
                    f"Código: {selected_assignment.get('code')} · "
                    f"Tipos: {' · '.join(selected_assignment.get('document_types') or []) or 'No informados'}"
                )
            trd_save, trd_approve = st.columns(2)
            if trd_save.button(
                "Guardar cambio",
                use_container_width=True,
                key=f"save_trd_v6_{scope}_{record_id}",
            ):
                save_single_hierarchy(selected_record, selected_assignment, approve=False)
                st.success("Cambio guardado para revisión.")
                st.rerun()
            if trd_approve.button(
                "Aprobar documento",
                type="primary",
                use_container_width=True,
                key=f"approve_trd_v6_{scope}_{record_id}",
            ):
                save_single_hierarchy(selected_record, selected_assignment, approve=True)
                st.success("Documento aprobado.")
                st.rerun()

        elif assignment_mode == "Agregar serie manual":
            top_back, top_note = st.columns([1, 3])
            top_back.button(
                "Volver a la TRD",
                use_container_width=True,
                key=f"manual_back_v6_{scope}_{record_id}",
                on_click=_set_session_value,
                args=(mode_key, "TRD de PROINSALUD"),
            )
            top_note.caption("Use esta opción únicamente cuando la denominación no exista en la TRD activa.")
            manual_dep = st.selectbox(
                "Dependencia productora",
                options=dep_codes,
                index=dep_index,
                format_func=lambda code: next(f"{c} - {name}" for c, name in dep_pairs if c == code),
                key=f"manual_dep_v6_{scope}_{record_id}",
            )
            initial_series = ""
            initial_subseries = ""
            if current.get("is_other"):
                initial_series = str(current.get("series_name") or "")
                initial_subseries = str(current.get("subseries_name") or "")
                if initial_series == OTHER_SERIES_LABEL:
                    initial_series = ""
                if initial_subseries == OTHER_SUBSERIES_LABEL:
                    initial_subseries = ""
            manual_series_name = st.text_input(
                "Nombre de la nueva serie",
                value=initial_series,
                placeholder="Ejemplo: REGISTROS DE ...",
                key=f"manual_series_v6_{scope}_{record_id}",
            )
            manual_subseries_name = st.text_input(
                "Nombre de la subserie, si aplica",
                value=initial_subseries,
                key=f"manual_subseries_v6_{scope}_{record_id}",
            )
            manual_assignment = other_entry(manual_dep, dependency_name_from_code(manual_dep))
            if manual_series_name.strip():
                manual_assignment["series_name"] = manual_series_name.strip()
            if manual_subseries_name.strip():
                manual_assignment["subseries_name"] = manual_subseries_name.strip()
            manual_assignment["source"] = "OTROS / manual"
            resolved_manual = canonicalize_custom_entry(
                manual_assignment,
                entries,
                filename=str(selected_record.get("filename") or ""),
                extracted_text=str(selected_record.get("extracted_text") or ""),
            )
            if manual_series_name.strip() and not resolved_manual.get("is_other"):
                st.info(
                    f"La denominación ya existe en la TRD. Se reutilizará {resolved_manual.get('code')} y no se creará una carpeta duplicada."
                )
            manual_save, manual_approve = st.columns(2)
            if manual_save.button(
                "Guardar nueva serie",
                disabled=not bool(manual_series_name.strip()),
                use_container_width=True,
                key=f"save_manual_v6_{scope}_{record_id}",
            ):
                save_single_hierarchy(selected_record, resolved_manual, approve=False, notes="Serie agregada manualmente para validación.")
                st.success("Clasificación guardada para revisión.")
                st.rerun()
            if manual_approve.button(
                "Aprobar clasificación",
                type="primary",
                disabled=not bool(manual_series_name.strip()),
                use_container_width=True,
                key=f"approve_manual_v6_{scope}_{record_id}",
            ):
                save_single_hierarchy(selected_record, resolved_manual, approve=True, notes="Serie agregada manualmente para validación.")
                st.success("Documento aprobado.")
                st.rerun()

        else:
            top_back, top_link = st.columns([1, 2])
            top_back.button(
                "Volver a la TRD",
                use_container_width=True,
                key=f"banter_back_v6_{scope}_{record_id}",
                on_click=_set_session_value,
                args=(mode_key, "TRD de PROINSALUD"),
            )
            top_link.link_button("Abrir BANTER oficial", BANTER_SOURCE_URL, use_container_width=True)
            banter_dep = st.selectbox(
                "Dependencia productora",
                options=dep_codes,
                index=dep_index,
                format_func=lambda code: next(f"{c} - {name}" for c, name in dep_pairs if c == code),
                key=f"banter_dep_v6_{scope}_{record_id}",
            )
            default_query = f"{selected_record.get('filename', '')} {str(selected_record.get('extracted_text', ''))[:5000]}".strip()
            banter_query = st.text_area(
                "Documento o términos que desea consultar",
                value=default_query,
                height=110,
                key=f"banter_query_v6_{scope}_{record_id}",
            )
            if st.button(
                "Buscar en BANTER",
                type="primary",
                use_container_width=True,
                key=f"search_banter_v6_{scope}_{record_id}",
            ):
                st.session_state[f"banter_matches_v6_{scope}_{record_id}"] = banter_engine.search(banter_query, top_k=20)
            banter_matches = st.session_state.get(
                f"banter_matches_v6_{scope}_{record_id}",
                banter_engine.search(default_query, top_k=12),
            )
            selected_banter_term: dict[str, Any] | None = None
            if banter_matches:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Afinidad": item.get("score_percent", 0),
                                "Serie": item.get("series_name", ""),
                                "Subserie": item.get("subseries_name", "") or "No aplica",
                                "Definición": item.get("definition", ""),
                            }
                            for item in banter_matches
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                    height=300,
                    column_config={
                        "Afinidad": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")
                    },
                )
                selected_banter_index = st.selectbox(
                    "Resultado BANTER",
                    options=list(range(len(banter_matches))),
                    format_func=lambda idx: (
                        f"{banter_matches[idx].get('series_name', '')} · "
                        f"{banter_matches[idx].get('subseries_name') or 'No aplica'}"
                    ),
                    key=f"selected_banter_v6_{scope}_{record_id}",
                )
                selected_banter_term = banter_matches[int(selected_banter_index)]
            else:
                st.warning("No se encontraron coincidencias. Pruebe con el asunto principal del documento.")

            if selected_banter_term:
                custom_banter = to_custom_classification(
                    selected_banter_term,
                    banter_dep,
                    dependency_name_from_code(banter_dep),
                )
                resolved_assignment = canonicalize_custom_entry(
                    custom_banter,
                    entries,
                    filename=str(selected_record.get("filename") or ""),
                    extracted_text=str(selected_record.get("extracted_text") or ""),
                )
                if not resolved_assignment.get("is_other"):
                    st.info(
                        f"Esta denominación ya existe en la TRD. Se reutilizará {resolved_assignment.get('code')} y no se creará otra carpeta."
                    )
                banter_save, banter_approve = st.columns(2)
                if banter_save.button(
                    "Guardar resultado",
                    use_container_width=True,
                    key=f"save_banter_v6_{scope}_{record_id}",
                ):
                    save_single_hierarchy(
                        selected_record,
                        resolved_assignment,
                        approve=False,
                        notes="Búsqueda apoyada en BANTER AGN.",
                    )
                    st.success("Resultado guardado para revisión.")
                    st.rerun()
                if banter_approve.button(
                    "Aprobar resultado",
                    type="primary",
                    use_container_width=True,
                    key=f"approve_banter_v6_{scope}_{record_id}",
                ):
                    save_single_hierarchy(
                        selected_record,
                        resolved_assignment,
                        approve=True,
                        notes="Búsqueda apoyada en BANTER AGN.",
                    )
                    st.success("Documento aprobado.")
                    st.rerun()

def _reset_review_workspace() -> None:
    """Reinicia solo el estado visual de la tabla, sin borrar clasificaciones."""

    st.session_state["review_editor_revision_v8"] = int(st.session_state.get("review_editor_revision_v8", 0)) + 1
    st.session_state.pop("review_pending_table_v8", None)
    st.session_state.pop("review_marked_ids_v8", None)
    st.session_state.pop("review_series_filter_v8", None)


def _reset_review_editor_only() -> None:
    st.session_state["review_editor_revision_v8"] = int(st.session_state.get("review_editor_revision_v8", 0)) + 1
    st.session_state.pop("review_pending_table_v8", None)
    st.session_state.pop("review_marked_ids_v8", None)


def _records_with_dependency(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        copy["dependency_code"] = record_dependency_code(record)
        enriched.append(copy)
    return enriched


def render_review_workspace(*, focused: bool = False) -> None:
    records = db.list_classifications()
    if not records:
        st.info("Todavía no hay documentos para revisar.")
        if focused and st.button("Volver a la vista normal", use_container_width=True):
            st.session_state["review_focus_mode_v5"] = False
            st.rerun()
        return

    if focused:
        title_col, mode_col, exit_col = st.columns([5, 1.2, 1.2])
        title_col.markdown('<div class="focus-title">Revisión y aprobación · vista completa</div>', unsafe_allow_html=True)
        mode_col.toggle("Modo nocturno", key="dark_mode_v5")
        if exit_col.button("Volver", use_container_width=True, key="exit_review_focus_v8"):
            st.session_state["review_focus_mode_v5"] = False
            st.rerun()
    else:
        head_text, expand_col = st.columns([5, 1.4])
        head_text.caption(
            "Seleccione una dependencia y edite directamente serie y subserie. OTROS aparece primero; BANTER permanece separado."
        )
        if expand_col.button("Mostrar toda la tabla", use_container_width=True, key="open_review_focus_v8"):
            st.session_state["review_focus_mode_v5"] = True
            st.rerun()

    f1, f2, f3, f4 = st.columns([1.05, 1.35, 1.25, .8])
    statuses = f1.multiselect(
        "Estados",
        ["Pendiente", "Aprobada", "Corregida", "Descartada"],
        default=["Pendiente"],
        key="review_statuses_v8",
        on_change=_reset_review_workspace,
    )
    status_records = [record for record in records if record.get("status") in statuses]
    catalog_dep_pairs = dependency_options(entries)
    catalog_dep_codes = [code for code, _ in catalog_dep_pairs]
    enriched_status_records = _records_with_dependency(status_records)
    present_dep_codes = [
        code for code in catalog_dep_codes
        if any(record.get("dependency_code") == code for record in enriched_status_records)
    ]
    dep_state_key = "review_dependency_filter_v8"
    if dep_state_key not in st.session_state:
        st.session_state[dep_state_key] = preferred_dependency_code(
            enriched_status_records,
            catalog_dep_codes,
        )
    elif st.session_state.get(dep_state_key) not in ([""] + catalog_dep_codes):
        st.session_state[dep_state_key] = preferred_dependency_code(
            enriched_status_records,
            catalog_dep_codes,
        )
    elif (
        st.session_state.get(dep_state_key)
        and present_dep_codes
        and st.session_state.get(dep_state_key) not in present_dep_codes
    ):
        st.session_state[dep_state_key] = present_dep_codes[0]

    dep_filter = f2.selectbox(
        "Dependencia de trabajo",
        options=[""] + catalog_dep_codes,
        format_func=lambda code: (
            "Todas (solo consulta)"
            if not code
            else next(f"{c} - {name}" for c, name in catalog_dep_pairs if c == code)
        ),
        key=dep_state_key,
        help=(
            "La dependencia se selecciona automáticamente al abrir la revisión. "
            "Las series de la tabla pertenecen únicamente a esta dependencia."
        ),
        on_change=_reset_review_workspace,
    )
    scoped_series = series_options_for_dependency(entries, dep_filter, OTHER_SERIES_LABEL) if dep_filter else [OTHER_SERIES_LABEL]
    official_scoped_series = [value for value in scoped_series if value != OTHER_SERIES_LABEL]
    series_filter = f3.selectbox(
        "Serie visible",
        options=[""] + official_scoped_series,
        format_func=lambda value: "Todas las series" if not value else value,
        disabled=not bool(dep_filter),
        key="review_series_filter_v8",
        help=(
            "Este filtro es opcional. Si elige una serie, el desplegable de subseries "
            "queda limitado a las subseries oficiales de esa serie."
        ),
        on_change=_reset_review_editor_only,
    )
    with f4.popover("Columnas", use_container_width=True):
        available_columns = [column for column in review_rows_dataframe(records).columns if column != "id"]
        selected_columns = _selected_review_columns(available_columns)

    if not dep_filter:
        st.warning(
            "La vista ‘Todas’ es solo de consulta. Seleccione una dependencia para recuperar los desplegables editables de serie y subserie."
        )

    visible = [
        record
        for record in records
        if record.get("status") in statuses
        and (not dep_filter or record_dependency_code(record) == dep_filter)
        and (not series_filter or record_series_name(record) == series_filter)
    ][:1000]
    review_df = review_rows_dataframe(visible)
    if review_df.empty:
        st.info("No hay documentos que coincidan con los filtros.")
        return

    pending_rows = st.session_state.pop("review_pending_table_v8", None)
    if pending_rows:
        review_df = merge_editor_subset(review_df, pd.DataFrame(pending_rows))

    current_entries = [effective_review_entry(record) for record in visible]
    if dep_filter:
        editor_dependencies = [dependency_label(dep_filter, dependency_name_from_code(dep_filter))]
        editor_series = series_options_for_dependency(entries, dep_filter, OTHER_SERIES_LABEL)
        if series_filter:
            editor_subseries = subseries_options_for_series(
                entries,
                dep_filter,
                series_filter,
                OTHER_SUBSERIES_LABEL,
                include_no_apply=True,
            )
        else:
            dep_entries = [entry for entry in entries if str(entry.get("dependency_code") or "") == dep_filter]
            editor_subseries = ordered_archival_options(
                (entry.get("subseries_name") for entry in dep_entries),
                OTHER_SUBSERIES_LABEL,
                include_no_apply=True,
            )
    else:
        editor_dependencies = sorted(
            set(dependency_labels)
            | {
                dependency_label(
                    str(entry.get("dependency_code") or ""),
                    str(entry.get("dependency_name") or ""),
                )
                for entry in current_entries
            }
        )
        if "Dependencia por definir" not in editor_dependencies:
            editor_dependencies.insert(0, "Dependencia por definir")
        editor_series = list(all_series_options)
        editor_subseries = list(all_subseries_options)

    marked_ids = {int(value) for value in st.session_state.get("review_marked_ids_v8", [])}
    if marked_ids:
        review_df.loc[:, "Aprobar"] = review_df["id"].map(lambda value: int(value) in marked_ids)

    selected_columns = [column for column in selected_columns if column in review_df.columns]
    if not selected_columns:
        selected_columns = ["Archivo", "Serie", "Subserie"]
    display_columns = ["id", *selected_columns]
    display_df = review_df[display_columns].copy()
    editor_height = 760 if focused else min(680, max(250, 72 + len(review_df) * 35))
    disabled_columns = [
        column
        for column in ["Código", "Fuente", "Archivo", "Predicción IA", "Probabilidad", "Estado actual", "Evidencia"]
        if column in display_df.columns
    ]
    if not dep_filter:
        disabled_columns.extend(
            column for column in ["Dependencia", "Serie", "Subserie"]
            if column in display_df.columns and column not in disabled_columns
        )
    config = _review_editor_column_config(editor_dependencies, editor_series, editor_subseries)
    revision = int(st.session_state.get("review_editor_revision_v8", 0))
    editor_key = f"review_editor_v8_{'focus' if focused else 'normal'}_{revision}"
    edited_subset = st.data_editor(
        display_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=editor_height,
        disabled=disabled_columns,
        column_config={key: value for key, value in config.items() if key in display_df.columns or key == "id"},
        key=editor_key,
    )
    edited = merge_editor_subset(review_df, edited_subset)
    current_marked = {
        int(row["id"])
        for row in edited.to_dict(orient="records")
        if bool(row.get("Aprobar"))
    }
    st.session_state["review_marked_ids_v8"] = sorted(current_marked)

    mark_col, clear_col, count_col = st.columns([1.15, 1.15, 2.7])
    if mark_col.button(
        "Marcar todos",
        type="primary",
        use_container_width=True,
        key=f"mark_all_review_v8_{focused}",
        help="Marca la casilla Aprobar de todos los documentos visibles, sin aprobarlos todavía.",
    ):
        marked_table = set_boolean_column(edited, "Aprobar", True)
        st.session_state["review_pending_table_v8"] = marked_table.to_dict(orient="records")
        st.session_state["review_marked_ids_v8"] = [int(value) for value in marked_table["id"].tolist()]
        st.session_state["review_editor_revision_v8"] = revision + 1
        st.rerun()
    if clear_col.button(
        "Desmarcar todos",
        use_container_width=True,
        key=f"clear_all_review_v8_{focused}",
    ):
        cleared_table = set_boolean_column(edited, "Aprobar", False)
        st.session_state["review_pending_table_v8"] = cleared_table.to_dict(orient="records")
        st.session_state["review_marked_ids_v8"] = []
        st.session_state["review_editor_revision_v8"] = revision + 1
        st.rerun()
    count_col.caption(
        f"{len(current_marked)} de {len(edited)} documento(s) marcados. "
        "Marcar no aprueba: revise la jerarquía y después use ‘Aprobar marcados’."
    )

    action_1, action_2 = st.columns(2)
    if action_1.button(
        "Guardar cambios",
        type="primary",
        disabled=edited.empty,
        use_container_width=True,
        key=f"save_review_table_v8_{focused}",
    ):
        saved, _ = save_review_table(edited, mode="save")
        st.session_state["review_editor_revision_v8"] = revision + 1
        st.session_state.pop("review_pending_table_v8", None)
        st.success(f"Se guardaron {saved} registros.")
        st.rerun()
    if action_2.button(
        "Aprobar marcados",
        type="primary",
        disabled=edited.empty or not bool(current_marked),
        use_container_width=True,
        key=f"approve_selected_v8_{focused}",
    ):
        saved, approved_count = save_review_table(edited, mode="marked")
        st.session_state["review_marked_ids_v8"] = []
        st.session_state.pop("review_pending_table_v8", None)
        st.session_state["review_editor_revision_v8"] = revision + 1
        if approved_count:
            st.success(f"Se aprobaron {approved_count} documentos y se guardaron {saved} filas.")
            st.rerun()
        else:
            st.warning("Marque al menos una casilla en la columna Aprobar.")

    selected_rows = [row for row in edited.to_dict(orient="records") if bool(row.get("Seleccionar"))]
    if selected_rows:
        selected_row = selected_rows[0]
        selected_record = next(
            record
            for record in visible
            if int(record["id"]) == int(selected_row["id"])
        )
        if len(selected_rows) > 1:
            st.caption("Se abrió la primera fila seleccionada. Desmarque las demás para cambiar de documento.")
        _render_selected_document_editor(selected_record, selected_row, focused=focused)

    if not focused:
        st.divider()
        st.button(
            "Finalizar revisión y ver documentos aprobados",
            type="primary",
            use_container_width=True,
            on_click=navigate_to,
            args=("4. Documentos aprobados",),
            key="finish_review_v8",
        )


# Estado y mapas compartidos
db, catalog, classifier = initialize()
entries = catalog["entries"]
catalog_by_code = {str(entry.get("code", "")): entry for entry in entries if entry.get("code")}
key_to_entry, key_to_label, label_to_key = build_classification_options(entries)
all_option_labels = list(label_to_key.keys())
if BANTER_PATH.exists():
    banter_metadata, banter_terms = load_banter_reference(BANTER_PATH)
else:
    banter_metadata, banter_terms = {}, [
        {
            "series_name": "OTROS / OTRAS SERIES",
            "subseries_name": "Clasificación por validar",
            "definition": "Término temporal para revisión archivística.",
            "aliases": ["otros"],
            "document_types": [],
        }
    ]
banter_engine = get_banter_engine(json.dumps(banter_terms, ensure_ascii=False, sort_keys=True))
dependency_labels = [dependency_label(code, name) for code, name in dependency_options(entries)]
all_series_options = ordered_archival_options(
    (entry.get("series_name") for entry in entries),
    OTHER_SERIES_LABEL,
)
all_subseries_options = ordered_archival_options(
    (entry.get("subseries_name") for entry in entries),
    OTHER_SUBSERIES_LABEL,
    include_no_apply=True,
)
source_options = ["TRD PROINSALUD", "BANTER AGN (orientativo)", "OTROS / manual"]
counts = db.counts()

NAV_OPTIONS = [
    "Inicio",
    "1. Administración TRD/CCD",
    "2. TRD e instrumentos",
    "3. Clasificación y revisión",
    "4. Documentos aprobados",
    "5. Carpetas masivas",
    "6. Catálogo y BANTER",
    "Ayuda",
]
if st.session_state.get("main_navigation") not in NAV_OPTIONS:
    st.session_state["main_navigation"] = "Inicio"

with st.sidebar:
    st.markdown(
        '<div class="institution-badge">PROINSALUD S.A.<br><span style="font-size:.78rem;font-weight:400">Clasificador documental</span></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    page = st.radio(
        "Navegación",
        NAV_OPTIONS,
        label_visibility="collapsed",
        key="main_navigation",
    )
    if not st.session_state.get("review_focus_mode_v5"):
        st.toggle("Modo nocturno", key="dark_mode_v5")
    st.divider()
    st.caption("Catálogo activo")
    st.write(f"**{catalog['name']}**")
    st.caption(f"{len(entries):,} clasificaciones · {len(dependency_options(entries))} dependencias")
    st.caption(f"Modelo local: {MODEL_VERSION}")
    st.caption(f"BANTER local: {len(banter_terms):,} términos")
    st.caption(f"Versión: {APP_VERSION}")

st.markdown(
    """
    <div class="hero">
      <h1>Gestión documental PROINSALUD</h1>
      <p>Cargue, revise, apruebe y genere la estructura de carpetas en un flujo único.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

workflow_pages = [
    "1. Administración TRD/CCD",
    "2. TRD e instrumentos",
    "3. Clasificación y revisión",
    "4. Documentos aprobados",
    "5. Carpetas masivas",
    "6. Catálogo y BANTER",
]
workflow_labels = ["1 Administrar", "2 Consultar TRD", "3 Clasificar", "4 Aprobar", "5 Exportar", "6 Buscar"]
active_index = workflow_pages.index(page) if page in workflow_pages else -1
workflow_html = '<div class="workflow">' + ''.join(
    f'<span class="{"active" if index == active_index else ""}">{label}</span>'
    for index, label in enumerate(workflow_labels)
) + '</div>'
st.markdown(workflow_html, unsafe_allow_html=True)


if page == "Inicio":
    st.subheader("Panel general")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Clasificaciones TRD", f"{len(entries):,}")
    c2.metric("Documentos procesados", f"{counts['total']:,}")
    c3.metric("Pendientes", f"{counts['pending']:,}")
    c4.metric("Aprobados / corregidos", f"{counts['reviewed']:,}")

    st.markdown("### Flujo de trabajo")
    cards = [
        ("1", "Administrar", "Cargue, active o retire versiones TRD/CCD desde el módulo protegido.", "1. Administración TRD/CCD"),
        ("2", "TRD e instrumentos", "Visualice y descargue cada TRD, el CCD por área y el organigrama institucional.", "2. TRD e instrumentos"),
        ("3", "Clasificar y revisar", "Seleccione el alcance, cargue el lote, procese con OCR y corrija la jerarquía.", "3. Clasificación y revisión"),
        ("4", "Aprobados", "Visualice los documentos finalizados y descargue la tabla en Excel, CSV, JSON o PDF.", "4. Documentos aprobados"),
        ("5", "Generar carpetas", "Cree el ZIP sobre la estructura masiva codificada entregada por PROINSALUD.", "5. Carpetas masivas"),
        ("6", "Buscar", "Consulte series y subseries de la TRD activa y use BANTER como fuente orientativa.", "6. Catálogo y BANTER"),
    ]
    columns = st.columns(3)
    for index, (number, title, text, destination) in enumerate(cards):
        column = columns[index % 3]
        with column:
            st.markdown(
                f'<div class="module-card"><span class="step-badge">MÓDULO {number}</span><h3>{title}</h3><p>{text}</p></div>',
                unsafe_allow_html=True,
            )
            st.button(
                f"Abrir módulo {number}",
                use_container_width=True,
                key=f"home_open_module_{number}",
                on_click=navigate_to,
                args=(destination,),
            )
    st.write("")
    st.info(
        "La afinidad indica semejanza entre el documento y la TRD; la aprobación final siempre corresponde al responsable de gestión documental. "
        "Los documentos no cubiertos por la TRD se marcan temporalmente como OTROS / OTRAS SERIES, sin asignarles un código oficial inventado."
    )

elif page == "1. Administración TRD/CCD":
    st.subheader("Administración privada de instrumentos archivísticos")
    if not st.session_state.get("admin_authorized"):
        st.markdown(
            '<div class="soft-panel"><b>Acceso restringido.</b><br>Este módulo permite modificar las fuentes que alimentan el clasificador.</div>',
            unsafe_allow_html=True,
        )
        supplied = st.text_input("Contraseña de administración", type="password", key="admin_password_input")
        if st.button("Ingresar", type="primary", use_container_width=True):
            if hmac.compare_digest(supplied, configured_admin_password()):
                st.session_state["admin_authorized"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    else:
        top_left, top_right = st.columns([4, 1])
        top_left.success("Sesión administrativa habilitada.")
        if top_right.button("Cerrar sesión", use_container_width=True):
            st.session_state.pop("admin_authorized", None)
            st.rerun()

        upload_tab, versions_tab, sources_tab = st.tabs(["Cargar nueva versión", "Activar o eliminar", "Fuentes institucionales"])
        with upload_tab:
            uploads = st.file_uploader(
                "TRD o CCD en Excel, CSV, ZIP o RAR",
                type=["xlsx", "xlsm", "xls", "csv", "tsv", "zip", "rar"],
                accept_multiple_files=True,
                key="admin_table_uploads",
            )
            version_name = st.text_input("Nombre de la versión", value=f"Actualización TRD/CCD {datetime.now():%Y-%m-%d}")
            if st.button("Analizar instrumentos", type="primary", disabled=not uploads, use_container_width=True):
                with st.spinner("Leyendo dependencias, series, subseries, retención y disposición final…"):
                    source_files, _source_errors = expand_table_uploads(uploads)
                    build = build_catalog_from_files(uploads)
                st.session_state["catalog_preview"] = {
                    "entries": build.entries,
                    "errors": build.errors,
                    "sources": build.sources,
                    "source_files": [{"name": name, "data": data} for name, data in source_files],
                    "stats": build.stats,
                    "trd_rows": build.trd_rows,
                    "ccd_rows": build.ccd_rows,
                    "name": version_name,
                }
            preview = st.session_state.get("catalog_preview")
            if preview:
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Registros", preview["stats"]["registros"])
                s2.metric("Dependencias", preview["stats"]["dependencias"])
                s3.metric("Filas TRD", preview["trd_rows"])
                s4.metric("Filas CCD", preview["ccd_rows"])
                for error in preview["errors"]:
                    st.warning(error)
                if preview["entries"]:
                    st.dataframe(entry_table(preview["entries"]), use_container_width=True, hide_index=True, height=340)
                    if st.button("Activar esta nueva versión", type="primary", use_container_width=True):
                        new_catalog_id = db.save_catalog(
                            preview["name"],
                            preview["entries"],
                            {"fuentes": preview["sources"], "estadisticas": preview["stats"]},
                        )
                        persist_catalog_sources(
                            CATALOG_SOURCE_DIR,
                            new_catalog_id,
                            preview.get("source_files") or [],
                        )
                        get_classifier.clear()
                        st.session_state.pop("catalog_preview", None)
                        st.success("La versión fue guardada y activada con sus archivos fuente.")
                        st.rerun()

        with versions_tab:
            versions = db.list_catalogs()
            version_labels = {
                version["id"]: f"#{version['id']} · {version['name']} · {version['created_at'][:10]}" + (" · ACTIVA" if version["is_active"] else "")
                for version in versions
            }
            selected_version = st.selectbox(
                "Versiones disponibles",
                options=[version["id"] for version in versions],
                format_func=lambda value: version_labels[value],
            )
            active_col, delete_col = st.columns(2)
            if active_col.button(
                "Activar versión seleccionada",
                disabled=selected_version == catalog["id"],
                use_container_width=True,
                type="primary",
            ):
                db.activate_catalog(selected_version)
                get_classifier.clear()
                st.rerun()
            confirm_delete = delete_col.checkbox("Confirmo que deseo retirarla", key="confirm_catalog_delete")
            if delete_col.button(
                "Eliminar / archivar versión",
                disabled=selected_version == catalog["id"] or not confirm_delete,
                use_container_width=True,
            ):
                try:
                    outcome = db.delete_catalog(selected_version)
                    st.success("Versión eliminada." if outcome == "deleted" else "Versión retirada de la lista y conservada para trazabilidad histórica.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            st.caption("Las versiones utilizadas por documentos históricos se archivan en lugar de destruirse, para conservar la trazabilidad.")

        with sources_tab:
            active_source_records = load_catalog_sources(CATALOG_SOURCE_DIR, catalog["id"], SOURCE_TRD_PATH)
            d1, d2, d3 = st.columns(3)
            d1.download_button(
                "Descargar catálogo normalizado",
                data=json.dumps({"metadata": catalog["metadata"], "entries": entries}, ensure_ascii=False, indent=2),
                file_name="catalogo_trd_ccd_proinsalud.json",
                mime="application/json",
                use_container_width=True,
            )
            if active_source_records:
                d2.download_button(
                    "Descargar Excel fuente activos",
                    data=source_bundle_bytes(active_source_records),
                    file_name=f"fuentes_catalogo_{catalog['id']}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            if MASSIVE_TEMPLATE_PATH.exists():
                d3.download_button(
                    "Descargar plantilla de carpetas",
                    data=MASSIVE_TEMPLATE_PATH.read_bytes(),
                    file_name="plantilla_carpetas_masivas.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

elif page == "2. TRD e instrumentos":
    st.subheader("Tablas de retención e instrumentos archivísticos")
    st.caption(
        "Consulte una tabla a la vez, visualice el Excel que alimentó el catálogo activo y descargue el archivo original o una copia normalizada."
    )
    default_source_fallback = (
        SOURCE_TRD_PATH
        if str(catalog.get("metadata", {}).get("origen", "")) == DEFAULT_CATALOG.name
        or not catalog.get("metadata", {}).get("fuentes")
        else None
    )
    instrument_sources = load_catalog_sources(
        CATALOG_SOURCE_DIR,
        catalog["id"],
        default_source_fallback,
    )
    trd_instrument_tab, ccd_instrument_tab, organigram_instrument_tab = st.tabs(
        ["Tablas de retención", "Cuadro de clasificación documental", "Organigrama"]
    )

    with trd_instrument_tab:
        st.markdown("### Tabla de retención por dependencia")
        dep_pairs = dependency_options(entries)
        selected_trd_dependency = st.selectbox(
            "Seleccione el área o dependencia",
            options=[code for code, _name in dep_pairs],
            format_func=lambda code: next(
                f"{dep_code} - {dep_name}" for dep_code, dep_name in dep_pairs if dep_code == code
            ),
            key="instrument_trd_dependency_v9",
        )
        selected_dependency_name = next(
            dep_name for dep_code, dep_name in dep_pairs if dep_code == selected_trd_dependency
        )
        selected_trd_entries = [
            entry for entry in entries if str(entry.get("dependency_code", "")) == selected_trd_dependency
        ]
        original_trd = find_trd_source(
            instrument_sources,
            selected_trd_dependency,
            selected_dependency_name,
        )
        normalized_trd_frame = entry_table(selected_trd_entries)

        m1, m2, m3 = st.columns(3)
        m1.metric("Registros", len(selected_trd_entries))
        m2.metric("Series", len({entry.get("series_code") for entry in selected_trd_entries}))
        m3.metric(
            "Subseries",
            len({entry.get("subseries_code") for entry in selected_trd_entries if entry.get("subseries_code")}),
        )

        download_normalized, download_original = st.columns(2)
        download_normalized.download_button(
            "Descargar tabla normalizada",
            data=dataframe_to_xlsx_bytes(
                normalized_trd_frame,
                f"TRD {selected_trd_dependency}",
            ),
            file_name=f"{selected_trd_dependency}_TRD_{selected_dependency_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        if original_trd:
            download_original.download_button(
                "Descargar Excel original cargado",
                data=bytes(original_trd.get("data", b"")),
                file_name=Path(str(original_trd.get("name", "TRD.xlsx"))).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        original_view, normalized_view = st.tabs(["Excel original", "Vista normalizada"])
        with original_view:
            if original_trd:
                st.caption(f"Archivo fuente: {original_trd.get('name', '')}")
                try:
                    trd_sheets = workbook_sheet_names(
                        str(original_trd.get("name", "")),
                        bytes(original_trd.get("data", b"")),
                    )
                    selected_trd_sheet = st.selectbox(
                        "Hoja del Excel",
                        options=trd_sheets,
                        index=preferred_sheet_index(
                            trd_sheets,
                            selected_trd_dependency,
                            selected_dependency_name,
                        ),
                        key=f"instrument_trd_sheet_{catalog['id']}_{selected_trd_dependency}",
                    )
                    raw_trd_frame = read_source_sheet(
                        str(original_trd.get("name", "")),
                        bytes(original_trd.get("data", b"")),
                        selected_trd_sheet,
                    )
                    st.dataframe(
                        raw_trd_frame,
                        use_container_width=True,
                        hide_index=True,
                        height=620,
                    )
                except Exception as exc:
                    st.warning(f"No fue posible mostrar la hoja original: {exc}")
            else:
                st.info(
                    "Esta versión no conserva el Excel original en el almacenamiento local. "
                    "La vista normalizada sigue disponible y puede descargarse."
                )
        with normalized_view:
            search_trd = st.text_input(
                "Buscar dentro de esta tabla",
                placeholder="Código, serie, subserie o tipo documental",
                key="instrument_trd_search_v9",
            )
            visible_trd_entries = selected_trd_entries
            if search_trd.strip():
                needle = search_trd.casefold()
                visible_trd_entries = [
                    entry
                    for entry in selected_trd_entries
                    if needle in str(entry.get("search_text", "")).casefold()
                ]
            st.dataframe(
                entry_table(visible_trd_entries),
                use_container_width=True,
                hide_index=True,
                height=620,
            )

    with ccd_instrument_tab:
        st.markdown("### Cuadro de clasificación documental por área")
        ccd_dependency = st.selectbox(
            "Área para visualizar",
            options=[""] + [code for code, _name in dependency_options(entries)],
            format_func=lambda code: "Todas las áreas" if not code else next(
                f"{dep_code} - {dep_name}"
                for dep_code, dep_name in dependency_options(entries)
                if dep_code == code
            ),
            key="instrument_ccd_dependency_v9",
        )
        ccd_entries = [
            entry
            for entry in entries
            if not ccd_dependency or str(entry.get("dependency_code", "")) == ccd_dependency
        ]
        ccd_frame = hierarchy_table(ccd_entries)
        ccd_original = find_ccd_source(instrument_sources)
        ccd_download, ccd_original_download = st.columns(2)
        ccd_download.download_button(
            "Descargar CCD del filtro",
            data=dataframe_to_xlsx_bytes(
                ccd_frame,
                f"CCD {ccd_dependency or 'GENERAL'}",
            ),
            file_name=f"CCD_{ccd_dependency or 'TODAS_LAS_AREAS'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        if ccd_original:
            ccd_original_download.download_button(
                "Descargar CCD original cargado",
                data=bytes(ccd_original.get("data", b"")),
                file_name=Path(str(ccd_original.get("name", "CCD PROINSALUD.xlsx"))).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        ccd_filtered_view, ccd_original_view = st.tabs(["Vista por área", "Excel original"])
        with ccd_filtered_view:
            ccd_search_v9 = st.text_input(
                "Buscar en el cuadro",
                placeholder="Dependencia, código, serie o subserie",
                key="instrument_ccd_search_v9",
            )
            visible_ccd_entries = ccd_entries
            if ccd_search_v9.strip():
                needle = ccd_search_v9.casefold()
                visible_ccd_entries = [
                    entry
                    for entry in ccd_entries
                    if needle in str(entry.get("search_text", "")).casefold()
                ]
            st.dataframe(
                hierarchy_table(visible_ccd_entries),
                use_container_width=True,
                hide_index=True,
                height=620,
            )
        with ccd_original_view:
            if ccd_original:
                try:
                    ccd_sheets = workbook_sheet_names(
                        str(ccd_original.get("name", "")),
                        bytes(ccd_original.get("data", b"")),
                    )
                    selected_ccd_sheet = st.selectbox(
                        "Hoja del CCD",
                        options=ccd_sheets,
                        key=f"instrument_ccd_sheet_{catalog['id']}",
                    )
                    raw_ccd_frame = read_source_sheet(
                        str(ccd_original.get("name", "")),
                        bytes(ccd_original.get("data", b"")),
                        selected_ccd_sheet,
                    )
                    st.dataframe(raw_ccd_frame, use_container_width=True, hide_index=True, height=620)
                except Exception as exc:
                    st.warning(f"No fue posible mostrar el CCD original: {exc}")
            else:
                st.info("No se encontró un Excel CCD original asociado con la versión activa.")

    with organigram_instrument_tab:
        st.markdown("### Organigrama institucional")
        st.caption("Visualización en alta resolución. Puede ampliar la imagen desde el navegador o descargar el PDF.")
        if ORGANIGRAM_PATH.exists():
            try:
                organigram_pages = pdf_page_count(ORGANIGRAM_PATH)
                organigram_page = st.number_input(
                    "Página del organigrama",
                    min_value=1,
                    max_value=max(1, organigram_pages),
                    value=1,
                    step=1,
                    key="organigram_page_v9",
                )
                st.image(
                    render_pdf_page(ORGANIGRAM_PATH, int(organigram_page), zoom=2.4),
                    caption=f"Organigrama PROINSALUD · página {int(organigram_page)} de {organigram_pages}",
                    use_container_width=True,
                )
                st.download_button(
                    "Descargar organigrama en PDF",
                    data=ORGANIGRAM_PATH.read_bytes(),
                    file_name="Organigrama_PROINSALUD.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as exc:
                st.warning(f"No fue posible visualizar el organigrama: {exc}")
        else:
            st.warning("No se encontró el organigrama institucional dentro del aplicativo.")

elif page == "3. Clasificación y revisión":
    if st.session_state.get("review_focus_mode_v5"):
        render_review_workspace(focused=True)
        st.stop()

    st.subheader("Clasificación y revisión")
    st.caption("Primero procese el lote. Después seleccione una fila, ajuste la jerarquía y apruebe cada documento.")
    automatic_tab, review_tab, manual_tab = st.tabs(["Cargar y clasificar", "Revisar y aprobar", "Asignación manual"])

    with automatic_tab:
        st.markdown("### 1. Seleccione el alcance del lote")
        scope_choice = st.radio(
            "¿En qué dependencias se debe buscar la clasificación?",
            ["Seleccione una opción", "Todas las dependencias", "Una dependencia específica"],
            index=0,
            horizontal=True,
            key="classification_scope_v9",
        )
        dep_options = dependency_options(entries)
        selected_dep = ""
        scope_ready = False
        if scope_choice == "Todas las dependencias":
            scope_ready = True
            st.success(
                "El modelo comparará cada documento contra todas las dependencias de la TRD activa."
            )
        elif scope_choice == "Una dependencia específica":
            selected_dep = st.selectbox(
                "Busque y seleccione la dependencia productora",
                options=[""] + [code for code, _name in dep_options],
                format_func=lambda code: "Seleccione una dependencia" if not code else next(
                    f"{dep_code} - {dep_name}"
                    for dep_code, dep_name in dep_options
                    if dep_code == code
                ),
                key="classification_dependency_v9",
            )
            scope_ready = bool(selected_dep)
            if selected_dep:
                selected_name = next(name for code, name in dep_options if code == selected_dep)
                st.success(
                    f"El lote se clasificará únicamente dentro de {selected_dep} - {selected_name}."
                )
            else:
                st.info("Seleccione la dependencia para habilitar la carga de documentos.")
        else:
            st.info(
                "Primero elija si desea comparar con todas las dependencias o limitar el lote a una sola área."
            )

        if scope_ready:
            st.markdown("### 2. Configure la lectura")
            ocr_col, guide_col = st.columns([1, 1])
            with ocr_col:
                ocr_profile = st.selectbox(
                    "Lectura del documento",
                    ["OCR completo", "OCR inteligente", "Solo texto digital"],
                    index=0,
                    help=(
                        "OCR completo revisa todas las páginas hasta el límite configurado. "
                        "OCR inteligente revisa el encabezado y las páginas con poco texto."
                    ),
                    key="ocr_profile_v9",
                )
                ocr_state = tesseract_status()
                if ocr_state.get("available"):
                    st.success(
                        f"OCR local disponible · Tesseract {str(ocr_state.get('version', '')).splitlines()[0]}"
                    )
                elif ocr_profile != "Solo texto digital":
                    st.warning(
                        "Tesseract no fue detectado. Los PDF con capa digital se leerán, "
                        "pero los escaneados requieren instalar OCR."
                    )
            with guide_col:
                st.markdown(
                    '<div class="soft-panel"><b>Alcance seleccionado</b><br>'
                    + (
                        "Todas las dependencias de la TRD activa."
                        if not selected_dep
                        else dependency_label(selected_dep, dependency_name_from_code(selected_dep))
                    )
                    + "<br><br>Después de procesar, continúe en <b>Revisar y aprobar</b>.</div>",
                    unsafe_allow_html=True,
                )

            with st.expander("Opciones avanzadas", expanded=False):
                settings_1, settings_2, settings_3 = st.columns(3)
                with settings_1:
                    year_mode = st.radio(
                        "Año documental",
                        ["Detectar automáticamente", "Usar año fijo"],
                        key="year_mode_v9",
                    )
                    default_year = st.number_input(
                        "Año predeterminado",
                        1990,
                        CURRENT_YEAR + 1,
                        CURRENT_YEAR,
                        key="default_year_v9",
                    )
                with settings_2:
                    ocr_language = st.selectbox(
                        "Idioma OCR",
                        ["spa+eng", "spa", "eng"],
                        index=0,
                        key="ocr_language_v9",
                    )
                    max_ocr_pages = st.number_input(
                        "Máximo de páginas OCR",
                        1,
                        250,
                        50,
                        key="max_ocr_pages_v9",
                    )
                with settings_3:
                    top_k = st.slider(
                        "Alternativas por documento",
                        3,
                        12,
                        6,
                        key="top_k_v9",
                    )
                    st.caption(
                        "La probabilidad es una estimación relativa del modelo y siempre requiere validación humana."
                    )

            st.markdown("### 3. Cargue y procese los documentos")
            if "document_uploader_version" not in st.session_state:
                st.session_state["document_uploader_version"] = 0
            uploads = st.file_uploader(
                "Documentos individuales o archivo ZIP",
                type=DOCUMENT_UPLOAD_TYPES,
                accept_multiple_files=True,
                key=f"document_uploads_v9_{st.session_state['document_uploader_version']}",
            )
            process_col, clear_col = st.columns([2, 1])
            process_uploads = process_col.button(
                "Procesar lote",
                type="primary",
                disabled=not uploads,
                use_container_width=True,
                key="process_batch_v9",
            )
            if clear_col.button(
                "Limpiar lote temporal",
                use_container_width=True,
                key="clear_batch_v9",
            ):
                st.session_state.pop("last_results", None)
                st.session_state["document_uploader_version"] += 1
                st.rerun()

            if process_uploads:
                payloads, expansion_warnings = expand_document_uploads(uploads)
                for warning in expansion_warnings:
                    st.warning(warning)
                results = []
                progress = st.progress(0, text="Preparando documentos…")
                mode_map = {
                    "OCR completo": "all",
                    "OCR inteligente": "auto",
                    "Solo texto digital": "off",
                }
                selected_ocr_mode = mode_map[ocr_profile]
                for number, payload in enumerate(payloads, start=1):
                    progress.progress(
                        (number - 1) / max(len(payloads), 1),
                        text=f"Leyendo y clasificando: {payload.name}",
                    )
                    extracted = extract_document(
                        payload,
                        enable_ocr=selected_ocr_mode != "off",
                        ocr_language=ocr_language,
                        max_ocr_pages=int(max_ocr_pages),
                        ocr_mode=selected_ocr_mode,
                    )
                    if year_mode == "Usar año fijo":
                        year_result = {
                            "year": str(int(default_year)),
                            "source": "año fijo seleccionado para la carga",
                            "confidence": 1.0,
                        }
                    else:
                        year_result = detect_document_year(
                            payload.name,
                            extracted.text,
                            extracted.metadata,
                            default_year=int(default_year),
                        )
                    candidates = classifier.classify(
                        payload.name,
                        extracted.text,
                        dependency_code=selected_dep or None,
                        top_k=int(top_k),
                    )
                    candidates = fallback_candidates(
                        candidates,
                        selected_dep,
                        payload.name,
                        extracted.text,
                    )
                    document_id = db.save_document(payload, extracted)
                    classification_id = db.save_classification(
                        document_id,
                        catalog["id"],
                        candidates,
                        document_year=year_result["year"],
                        year_source=year_result["source"],
                        year_confidence=float(year_result.get("confidence", 0)),
                    )
                    results.append(
                        {
                            "classification_id": classification_id,
                            "sha256": payload.sha256,
                            "filename": payload.name,
                            "extracted": extracted,
                            "candidates": candidates,
                            "year": year_result,
                        }
                    )
                progress.progress(1.0, text=f"Listo: {len(results)} documento(s) procesado(s)")
                st.session_state["last_results"] = merge_results_by_sha(
                    st.session_state.get("last_results", []),
                    results,
                )
                st.success("Lote procesado. Continúe en la pestaña ‘Revisar y aprobar’.")

            last_results = st.session_state.get("last_results", [])
            if last_results:
                summary = []
                for result in last_results:
                    top = result["candidates"][0] if result["candidates"] else {}
                    metadata = result["extracted"].metadata or {}
                    summary.append(
                        {
                            "Archivo": result["filename"],
                            "Año": result["year"]["year"],
                            "Código": top.get("code") or "Sin código",
                            "Serie": top.get("series_name", ""),
                            "Subserie": top.get("subseries_name", "") or "No aplica",
                            "Probabilidad": top.get("score_percent", 0),
                            "Confianza": top.get("confidence", ""),
                            "OCR": (
                                f"{metadata.get('ocr_coverage_percent', 0)}%"
                                if metadata.get("pages")
                                else ("Sí" if metadata.get("ocr") else "No aplica")
                            ),
                        }
                    )
                st.dataframe(
                    pd.DataFrame(summary),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Probabilidad": st.column_config.ProgressColumn(
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        )
                    },
                )
                for preview_index, result in enumerate(last_results):
                    top = result["candidates"][0] if result["candidates"] else {}
                    with st.expander(
                        f"{result['filename']} · {top.get('series_name') or 'Sin clasificación'}"
                    ):
                        left, right = st.columns([1.15, 1])
                        with left:
                            candidate_frame = entry_table(result["candidates"], include_score=True)
                            st.dataframe(
                                candidate_frame,
                                use_container_width=True,
                                hide_index=True,
                                height=280,
                            )
                            if top.get("evidence"):
                                st.caption(
                                    "Evidencia principal: "
                                    + " · ".join(top.get("evidence") or [])
                                )
                        with right:
                            st.text_area(
                                "Contenido detectado",
                                result["extracted"].preview or "No se extrajo texto.",
                                height=280,
                                disabled=True,
                                key=preview_widget_key(
                                    result["classification_id"],
                                    preview_index,
                                    result.get("sha256", ""),
                                ),
                            )
                            for warning in result["extracted"].warnings:
                                st.warning(warning)
        else:
            st.warning("La carga documental se habilitará después de seleccionar el alcance del lote.")

    with review_tab:
        render_review_workspace(focused=False)

    with manual_tab:
        manual_dep = st.selectbox(
            "Dependencia",
            options=[code for code, _ in dependency_options(entries)],
            format_func=lambda code: next(f"{c} - {name}" for c, name in dependency_options(entries) if c == code),
            key="manual_dependency_v4",
        )
        manual_query = st.text_input("Nombre o descripción del documento", placeholder="Ej.: acta del comité de historias clínicas", key="manual_query_v4")
        if st.button("Buscar clasificación", type="primary", disabled=not manual_query.strip(), use_container_width=True, key="manual_search_v4"):
            st.session_state["manual_matches_v4"] = classifier.search(manual_query, dependency_code=manual_dep, top_k=30)
        manual_matches = st.session_state.get("manual_matches_v4", [])
        if manual_matches:
            st.dataframe(hierarchy_table(manual_matches, include_score=True), use_container_width=True, hide_index=True)
            selected_code = st.selectbox(
                "Clasificación final",
                options=[entry["code"] for entry in manual_matches],
                format_func=lambda code: standard_option_label(next(entry for entry in manual_matches if entry["code"] == code)),
                key="manual_code_v4",
            )
            manual_year = st.number_input("Año documental", 1990, CURRENT_YEAR + 1, CURRENT_YEAR, key="manual_year_v4")
            manual_uploads = st.file_uploader(
                "Documentos para esta clasificación",
                type=DOCUMENT_UPLOAD_TYPES,
                accept_multiple_files=True,
                key="manual_uploads_v4",
            )
            if st.button("Asignar y aprobar", type="primary", disabled=not manual_uploads, use_container_width=True, key="manual_assign_v4"):
                payloads, warnings = expand_document_uploads(manual_uploads)
                for warning in warnings:
                    st.warning(warning)
                selected_entry = next(entry for entry in manual_matches if entry["code"] == selected_code)
                candidate = {**selected_entry, "score": 1.0, "score_percent": 100.0, "confidence": "Manual"}
                for payload in payloads:
                    extracted = extract_document(payload, enable_ocr=True, ocr_language="spa+eng", max_ocr_pages=50, ocr_mode="all")
                    document_id = db.save_document(payload, extracted)
                    classification_id = db.save_classification(
                        document_id,
                        catalog["id"],
                        [candidate],
                        document_year=str(int(manual_year)),
                        year_source="asignación directa",
                        year_confidence=1.0,
                    )
                    db.update_review(
                        classification_id,
                        selected_code,
                        "Aprobada",
                        f"Asignación directa: {manual_query}",
                        document_year=int(manual_year),
                    )
                get_classifier.clear()
                st.success(f"{len(payloads)} documento(s) asignado(s) y aprobado(s).")

elif page == "4. Documentos aprobados":
    st.subheader("Consulta, visualización e impresión")
    approved = [record for record in db.list_classifications() if record.get("status") in {"Aprobada", "Corregida"}]
    if not approved:
        st.info("Aún no hay documentos aprobados o corregidos.")
    else:
        available_years = sorted({str(record.get("document_year") or "SIN_ANIO") for record in approved}, reverse=True)
        f1, f2, f3 = st.columns(3)
        years_filter = f1.multiselect("Años", available_years, default=available_years)
        dep_codes = sorted({record_dependency_code(record) for record in approved if record_dependency_code(record)})
        deps_filter = f2.multiselect(
            "Dependencias",
            dep_codes,
            default=dep_codes,
            format_func=lambda code: next((f"{c} - {name}" for c, name in dependency_options(entries) if c == code), code),
        )
        text_filter = f3.text_input("Buscar por nombre", placeholder="Nombre del archivo")
        visible = [
            record for record in approved
            if str(record.get("document_year") or "SIN_ANIO") in years_filter
            and (not deps_filter or record_dependency_code(record) in deps_filter)
            and (not text_filter or text_filter.casefold() in str(record.get("filename", "")).casefold())
        ]
        rows = manifest_rows(visible, entries)
        s1, s2, s3 = st.columns(3)
        s1.metric("Documentos aprobados", len(visible))
        s2.metric("Dependencias", len({record_dependency_code(record) for record in visible if record_dependency_code(record)}))
        s3.metric("Años", len({record.get("document_year") for record in visible}))
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=380)

        d1, d2, d3, d4 = st.columns(4)
        d1.download_button("Excel", to_xlsx_bytes(rows), "tabla_documentos_aprobados.xlsx", use_container_width=True)
        d2.download_button("PDF imprimible", to_pdf_bytes(rows, "Tabla de documentos aprobados"), "tabla_documentos_aprobados.pdf", mime="application/pdf", use_container_width=True)
        d3.download_button("CSV", to_csv_bytes(rows), "tabla_documentos_aprobados.csv", mime="text/csv", use_container_width=True)
        d4.download_button("JSON", to_json_bytes(rows), "tabla_documentos_aprobados.json", mime="application/json", use_container_width=True)

        selected_record = st.selectbox(
            "Visualizar documento",
            options=visible,
            format_func=lambda record: f"{record.get('document_year')} · {record.get('filename')}",
        )
        left, right = st.columns([1.2, 1])
        with left:
            render_document_preview(selected_record, f"approved_{selected_record['id']}")
        with right:
            row = manifest_rows([selected_record], entries)[0]
            st.write(f"**Código final:** {row['codigo_final'] or 'Sin código TRD'}")
            st.write(f"**Dependencia:** {row['dependencia']}")
            st.write(f"**Serie:** {row['serie']}")
            st.write(f"**Subserie:** {row['subserie'] or 'No aplica'}")
            st.write(f"**Retención:** gestión {row['retencion_gestion'] or '—'} / central {row['retencion_central'] or '—'}")
            st.write(f"**Disposición final:** {row['disposicion_final'] or 'Pendiente de definición'}")

elif page == "5. Carpetas masivas":
    st.subheader("Generar archivo ZIP con carpetas codificadas")
    approved = [record for record in db.list_classifications() if record.get("status") in {"Aprobada", "Corregida"}]
    if not approved:
        st.info("Apruebe documentos en el módulo 3 antes de generar las carpetas masivas.")
    else:
        available_years = sorted({str(record.get("document_year") or "SIN_ANIO") for record in approved}, reverse=True)
        dep_codes = sorted({record_dependency_code(record) for record in approved if record_dependency_code(record)})
        f1, f2 = st.columns(2)
        export_years = f1.multiselect("Años incluidos", available_years, default=available_years)
        export_dependencies = f2.multiselect(
            "Dependencias incluidas",
            dep_codes,
            default=dep_codes,
            format_func=lambda code: next((f"{c} - {name}" for c, name in dependency_options(entries) if c == code), code),
        )
        selected_records = [
            record for record in approved
            if str(record.get("document_year") or "SIN_ANIO") in export_years
            and (not export_dependencies or record_dependency_code(record) in export_dependencies)
        ]
        mode_label = st.radio(
            "Tipo de estructura",
            ["Plantilla de carpetas masivas codificadas (recomendada)", "Jerarquía por año / dependencia / serie / subserie"],
        )
        structure_mode = "massive" if mode_label.startswith("Plantilla") else "year"
        c1, c2 = st.columns(2)
        include_structure = c1.checkbox("Incluir también las carpetas vacías", value=True)
        organize_types = c2.checkbox(
            "Ubicar por tipo documental cuando sea identificable",
            value=True,
            disabled=structure_mode != "massive",
        )
        if structure_mode == "massive":
            st.code("CARPETAS_MASIVAS_ACTUALIZADAS / DEPENDENCIA / SERIE / SUBSERIE / TIPO DOCUMENTAL / archivo", language=None)
            st.info(
                "La exportación reutiliza exactamente los nombres de la plantilla institucional. "
                "Cuando una ruta oficial ya existe, no crea una segunda carpeta recortada; si la ruta es muy larga, "
                "solo ajusta el nombre del archivo. Si una denominación BANTER coincide con una serie o subserie de la TRD, "
                "reutiliza la carpeta codificada existente. Solo crea SERIE/SUBSERIE SIN CÓDIGO cuando no existe equivalencia oficial."
            )
            if not MASSIVE_TEMPLATE_PATH.exists():
                st.warning("No se encontró la plantilla institucional; se crearán las rutas a partir de la TRD activa.")
        else:
            st.code("AÑO / DEPENDENCIA / SERIE / SUBSERIE / archivo", language=None)
        rows = manifest_rows(selected_records, entries)
        st.metric("Documentos que se incluirán", len(rows))
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=320)

        signature_data = {
            "records": [[record.get("id"), record.get("updated_at"), record.get("final_code")] for record in selected_records],
            "years": export_years,
            "dependencies": export_dependencies,
            "structure_mode": structure_mode,
            "include_structure": include_structure,
            "organize_types": organize_types,
        }
        signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        prepared = st.session_state.get("prepared_massive_zip")
        if prepared and prepared.get("signature") != signature:
            st.session_state.pop("prepared_massive_zip", None)
            prepared = None

        if st.button("Preparar ZIP de carpetas masivas", type="primary", disabled=not selected_records, use_container_width=True):
            with st.spinner("Creando estructura y ubicando documentos aprobados…"):
                zip_bytes = build_classified_zip(
                    selected_records,
                    entries,
                    include_full_structure=include_structure,
                    years=export_years,
                    dependency_codes=export_dependencies,
                    structure_mode=structure_mode,
                    template_zip_path=MASSIVE_TEMPLATE_PATH if structure_mode == "massive" else None,
                    organize_by_document_type=organize_types,
                )
            st.session_state["prepared_massive_zip"] = {
                "signature": signature,
                "data": zip_bytes,
                "records": len(selected_records),
            }
            prepared = st.session_state["prepared_massive_zip"]
            st.success("ZIP preparado correctamente.")

        if prepared and prepared.get("signature") == signature:
            size_mb = len(prepared["data"]) / (1024 * 1024)
            st.info(f"Archivo listo: {prepared['records']} documento(s), {size_mb:.2f} MB.")
            st.download_button(
                "Descargar carpetas masivas clasificadas",
                data=prepared["data"],
                file_name="CARPETAS_MASIVAS_PROINSALUD_CLASIFICADAS.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
            )

elif page == "6. Catálogo y BANTER":
    st.subheader("Consulta inteligente de series y subseries")
    st.caption(
        "Busque primero en la TRD activa de PROINSALUD. Use BANTER únicamente como orientación cuando no exista una alternativa institucional adecuada."
    )
    search_tab, banter_tab = st.tabs(["Buscar en la TRD", "Buscar en BANTER"])

    with search_tab:
        query = st.text_area(
            "Describa el documento",
            placeholder="Ej.: contrato de arrendamiento con póliza, acta de liquidación y comunicaciones",
            height=100,
            key="catalog_search_query_v9",
        )
        search_dep = st.selectbox(
            "Limitar la búsqueda a una dependencia",
            options=[""] + [code for code, _name in dependency_options(entries)],
            format_func=lambda code: "Todas las dependencias" if not code else next(
                f"{dep_code} - {dep_name}"
                for dep_code, dep_name in dependency_options(entries)
                if dep_code == code
            ),
            key="catalog_search_dependency_v9",
        )
        number_results = st.slider(
            "Cantidad de resultados",
            5,
            40,
            15,
            key="catalog_search_results_v9",
        )
        if query.strip():
            matches = classifier.search(
                query,
                dependency_code=search_dep or None,
                top_k=number_results,
            )
            matches = fallback_candidates(matches, search_dep, query, query)
            st.dataframe(
                entry_table(matches, include_score=True),
                use_container_width=True,
                hide_index=True,
                height=480,
                column_config={
                    "Probabilidad": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    )
                },
            )
            official_matches = [match for match in matches if match.get("code")]
            if official_matches:
                selected_code = st.selectbox(
                    "Ver retención y disposición de una alternativa",
                    options=[entry["code"] for entry in official_matches],
                    format_func=lambda code: standard_option_label(
                        next(entry for entry in official_matches if entry.get("code") == code)
                    ),
                    key="catalog_search_detail_v9",
                )
                selected = next(
                    entry for entry in official_matches if entry.get("code") == selected_code
                )
                a, b, c = st.columns(3)
                a.metric("Archivo de gestión", selected.get("retention_management") or "—")
                b.metric("Archivo central", selected.get("retention_central") or "—")
                c.metric(
                    "Disposición",
                    " / ".join(selected.get("final_disposition") or []) or "—",
                )
                st.write(
                    "**Tipos documentales:**",
                    " · ".join(selected.get("document_types") or []) or "No informados",
                )
                st.write("**Procedimiento:**", selected.get("procedure") or "No informado")
            else:
                st.warning(
                    "No se encontró una coincidencia institucional suficiente. Revise OTROS en el módulo de aprobación o consulte BANTER."
                )

    with banter_tab:
        st.markdown("### BANTER como fuente orientativa")
        st.write(
            "Busque denominaciones externas para documentos que no aparecen en la TRD activa. "
            "El resultado no crea un código oficial y siempre requiere validación de Gestión Documental."
        )
        bq = st.text_area(
            "Documento, asunto o función",
            placeholder="Ej.: control de temperatura y humedad relativa del archivo central",
            height=100,
            key="banter_catalog_query_v9",
        )
        bcount = st.slider(
            "Cantidad de resultados BANTER",
            5,
            40,
            15,
            key="banter_catalog_count_v9",
        )
        if bq.strip():
            bmatches = banter_engine.search(bq, top_k=bcount)
            bdf = pd.DataFrame(
                [
                    {
                        "Afinidad": item.get("score_percent", 0),
                        "Serie": item.get("series_name", ""),
                        "Subserie": item.get("subseries_name", "") or "No aplica",
                        "Grupo funcional": item.get("functional_group", ""),
                        "Tipos documentales": " · ".join(item.get("document_types") or []),
                        "Definición": item.get("definition", ""),
                    }
                    for item in bmatches
                ]
            )
            st.dataframe(
                bdf,
                use_container_width=True,
                hide_index=True,
                height=500,
                column_config={
                    "Afinidad": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    )
                },
            )
        m1, m2, m3 = st.columns(3)
        m1.metric("Términos locales", len(banter_terms))
        m2.metric("Versión de referencia", str(banter_metadata.get("source_version") or "2.1"))
        m3.metric("Costo del modelo", "$0 / sin API")
        st.caption(
            str(
                banter_metadata.get("scope")
                or "Referencia orientativa; no reemplaza la TRD/CCD."
            )
        )
        st.link_button(
            "Consultar el BANTER oficial del AGN",
            BANTER_SOURCE_URL,
            use_container_width=True,
        )

    st.divider()
    st.caption(
        "Las TRD, el CCD y el organigrama se visualizan y descargan en el módulo 2: TRD e instrumentos."
    )

elif page == "Ayuda":
    st.subheader("Ayuda y criterios de uso")
    st.markdown(
        """
        **Administración privada.** La contraseña predeterminada del módulo 1 es `archivo123`. En producción puede cambiarse mediante la variable de entorno `ADMIN_PASSWORD` o los secretos de Streamlit.

        **TRD e instrumentos.** El módulo 2 permite abrir cada tabla de retención por dependencia, consultar el Excel original cargado, descargarlo, filtrar el CCD por área y visualizar el organigrama en alta resolución.

        **Clasificación asistida.** En el módulo 3 primero se selecciona el alcance: todas las dependencias o una dependencia específica. Solo después se habilita la carga. El motor combina el nombre del archivo, el texto extraído, OCR, dependencia, serie, subserie, tipos documentales y ejemplos previamente aprobados. La afinidad no reemplaza la decisión archivística.

        **Documentos fuera de tabla.** Se envían a `OTROS / OTRAS SERIES — sin código TRD`. Esta opción aparece primero en los desplegables; a continuación se muestran únicamente las series y subseries de la TRD activa. BANTER queda separado como última opción para proponer una denominación externa sin inventar un código oficial.

        **Aprobación.** En el módulo 3 puede editar dependencia, serie y subserie, abrir una fila en el editor jerárquico, usar `Marcar todos` y después `Aprobar marcados`, o marcar únicamente las filas necesarias. El botón `Mostrar toda la tabla` oculta los menús y ocupa todo el ancho; `Columnas visibles` permite simplificar la tabla sin perder la información oculta.

        **Modo nocturno.** El interruptor de la barra lateral cambia la paleta de toda la aplicación. En la vista completa de revisión el mismo control aparece en la barra superior.

        **OCR e IA local.** El perfil `OCR completo` revisa cada página hasta el límite configurado. El clasificador combina título principal, nombre del archivo, contenido completo, consenso entre páginas, tipología documental, similitud semántica y correcciones previamente aprobadas. No requiere una API de pago y los documentos se procesan localmente.

        **Carpetas masivas.** El módulo 5 conserva las rutas de la plantilla institucional. Si una propuesta BANTER o manual coincide con una serie/subserie ya codificada en la TRD, reutiliza la carpeta oficial y evita crear otra carpeta `SIN CÓDIGO`. Solo crea carpetas sin código cuando no existe equivalencia oficial. Para rutas largas se conserva la carpeta y se reduce únicamente el nombre físico del archivo.

        **Privacidad.** Los documentos se procesan localmente. La base está en `runtime/clasificador.sqlite3` y los originales en `runtime/uploads/`. Para producción se recomienda cifrado de disco, copias de seguridad, perfiles de acceso y auditoría.
        """
    )
    if INSTRUCTIONS_PATH.exists():
        with st.expander("Ver instructivo institucional incluido"):
            render_document_preview(
                {
                    "stored_path": str(INSTRUCTIONS_PATH),
                    "extension": ".pdf",
                    "filename": "Instructivo de gestión de carpetas TRD.pdf",
                    "extracted_text": "Instructivo institucional de gestión de carpetas TRD.",
                },
                "institutional_instructions",
            )
