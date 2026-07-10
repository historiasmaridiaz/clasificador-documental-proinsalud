from __future__ import annotations

import json
import os
import hmac
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core.catalog import build_catalog_from_files, load_catalog_json
from core.database import Database
from core.exporter import build_classified_zip, manifest_rows, to_csv_bytes, to_json_bytes, to_pdf_bytes, to_xlsx_bytes
from core.ml_engine import DocumentClassifier
from core.text_extract import detect_document_year, expand_document_uploads, extract_document
from core.ui_utils import merge_results_by_sha, pdf_page_count, preview_widget_key, render_pdf_page


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG = PROJECT_DIR / "data" / "catalogo_proinsalud.json"
ORGANIGRAM_PATH = PROJECT_DIR / "data" / "organigrama_proinsalud.pdf"
INSTRUCTIONS_PATH = PROJECT_DIR / "data" / "instructivo_gestion_carpetas_trd.pdf"
RUNTIME_DIR = Path(os.environ.get("CLASIFICADOR_DATA_DIR", PROJECT_DIR / "runtime"))
DOCUMENT_UPLOAD_TYPES = [
    "pdf", "docx", "xlsx", "xlsm", "xls", "pptx", "odt", "eml", "txt", "md", "csv", "tsv",
    "json", "xml", "html", "htm", "rtf", "log", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "zip",
]


st.set_page_config(
    page_title="Clasificador documental TRD/CCD",
    page_icon="🏥",
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


def require_optional_password() -> None:
    expected = configured_app_password()
    if not expected or st.session_state.get("access_authorized"):
        return
    st.title("Acceso al clasificador documental")
    supplied = st.text_input("Contraseña", type="password", key="app_access_password")
    if supplied:
        if hmac.compare_digest(supplied, expected):
            st.session_state["access_authorized"] = True
            st.rerun()
        st.error("Contraseña incorrecta.")
    st.stop()


require_optional_password()

st.markdown(
    """
    <style>
      :root {--pro-blue:#123F73; --pro-blue-2:#0C3C6C; --pro-orange:#E57900; --pro-pale:#EAF1F8;}
      .block-container {padding-top: 1.35rem; padding-bottom: 3rem; max-width: 1500px;}
      [data-testid="stSidebar"] {background:linear-gradient(180deg,#F2F7FC 0%,#E7F0F8 100%); border-right:1px solid #C8D8E8;}
      [data-testid="stMetric"] {background:white; border:1px solid #CCDCEB; border-top:4px solid var(--pro-orange); padding:.85rem; border-radius:.75rem; box-shadow:0 5px 16px rgba(18,63,115,.06);}
      .hero {display:flex;align-items:center;gap:1rem;padding:1.15rem 1.35rem;border-radius:1rem;background:linear-gradient(120deg,var(--pro-blue-2),var(--pro-blue) 72%,#20578E);color:white;margin-bottom:1rem;box-shadow:0 10px 30px rgba(12,60,108,.18);border-bottom:5px solid var(--pro-orange);}
      .brand-mark {width:58px;height:58px;display:grid;place-items:center;border-radius:50%;background:white;color:var(--pro-blue);font-weight:800;font-size:1.15rem;border:5px solid rgba(229,121,0,.9);flex:0 0 auto;}
      .hero h1 {font-size:1.75rem;margin:0 0 .25rem 0;}
      .hero p {margin:0;opacity:.93;}
      .small-note {font-size:.86rem;color:#52606d;}
      .instruction-card {height:100%;padding:1rem;border-radius:.8rem;background:white;border:1px solid #D2E0ED;border-left:5px solid var(--pro-orange);box-shadow:0 4px 12px rgba(18,63,115,.06);}
      .instruction-card h3 {color:var(--pro-blue);margin:.05rem 0 .45rem;}
      .instruction-card p {margin:0;color:#3E5873;}
      .institution-badge {padding:.65rem .8rem;border-radius:.7rem;background:#123F73;color:white;text-align:center;font-weight:700;letter-spacing:.02em;}
      div[data-baseweb="tab-list"] {gap:.4rem;}
      button[data-baseweb="tab"] {background:#EAF1F8;border-radius:.55rem .55rem 0 0;padding:.55rem .8rem;}
      button[data-baseweb="tab"][aria-selected="true"] {background:#123F73;color:white;}
      .stButton > button[kind="primary"] {font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def get_database(path: str) -> Database:
    return Database(path)


@st.cache_resource(show_spinner=False)
def get_classifier(entries_json: str, examples_json: str) -> DocumentClassifier:
    return DocumentClassifier(json.loads(entries_json), json.loads(examples_json))


def initialize() -> tuple[Database, dict, DocumentClassifier]:
    db = get_database(str(RUNTIME_DIR))
    if DEFAULT_CATALOG.exists():
        default_entries = load_catalog_json(DEFAULT_CATALOG)
        db.seed_catalog(
            "PROINSALUD — catálogo inicial",
            default_entries,
            {"origen": "TRD PROINSALUD.rar", "preconfigurado": True},
        )
    catalog = db.active_catalog()
    examples = db.learned_examples()
    classifier = get_classifier(
        json.dumps(catalog["entries"], ensure_ascii=False, sort_keys=True),
        json.dumps(examples, ensure_ascii=False, sort_keys=True),
    )
    return db, catalog, classifier


def entry_table(entries: list[dict], include_score: bool = False) -> pd.DataFrame:
    rows = []
    for entry in entries:
        row = {
            "Código": entry.get("code", ""),
            "Dependencia": entry.get("dependency_name", ""),
            "Serie": entry.get("series_name", ""),
            "Subserie": entry.get("subseries_name", ""),
            "Tipos documentales": " • ".join(entry.get("document_types") or []),
            "Retención gestión": entry.get("retention_management", ""),
            "Retención central": entry.get("retention_central", ""),
            "Disposición": " | ".join(entry.get("final_disposition") or []),
        }
        if include_score:
            row = {
                "Similitud": entry.get("score_percent", 0),
                "Confianza": entry.get("confidence", ""),
                **row,
            }
        rows.append(row)
    return pd.DataFrame(rows)


def hierarchy_table(entries: list[dict], include_score: bool = True) -> pd.DataFrame:
    rows = []
    for entry in entries:
        section = " - ".join(
            value for value in [str(entry.get("section_code", "")), str(entry.get("section_name", ""))] if value
        )
        dependency = " - ".join(
            value for value in [str(entry.get("dependency_code", "")), str(entry.get("dependency_name", ""))] if value
        )
        series_code = ".".join(
            value for value in [str(entry.get("dependency_code", "")), str(entry.get("series_code", ""))] if value
        )
        series = " - ".join(value for value in [series_code, str(entry.get("series_name", ""))] if value)
        subseries = ""
        if entry.get("subseries_code"):
            subseries = " - ".join(
                value for value in [str(entry.get("code", "")), str(entry.get("subseries_name", ""))] if value
            )
        row = {
                "Código TRD": entry.get("code", ""),
                "Sección": section,
                "Subsección / Dependencia": dependency,
                "Serie": series,
                "Subserie": subseries or "No aplica",
            }
        if include_score:
            row["Similitud"] = entry.get("score_percent", 0)
            row["Confianza"] = entry.get("confidence", "")
        rows.append(row)
    return pd.DataFrame(rows)


def dependency_options(entries: list[dict]) -> list[tuple[str, str]]:
    values = {
        (str(e.get("dependency_code", "")), str(e.get("dependency_name", "")))
        for e in entries
        if e.get("dependency_code")
    }
    return sorted(values, key=lambda x: tuple(int(part) for part in x[0].split(".")))


def render_document_preview(record: dict, key_prefix: str) -> None:
    path = Path(str(record.get("stored_path", "")))
    extension = str(record.get("extension", "")).lower()
    if path.is_file() and extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        st.image(str(path), caption=record.get("filename", path.name), use_container_width=True)
    elif path.is_file() and extension == ".pdf":
        try:
            pages = pdf_page_count(path)
            page_number = st.number_input(
                "Página de la vista previa",
                min_value=1,
                max_value=max(1, pages),
                value=1,
                step=1,
                key=f"{key_prefix}_pdf_page",
            )
            preview_png = render_pdf_page(path, int(page_number))
            st.image(
                preview_png,
                caption=f"{record.get('filename', path.name)} · página {int(page_number)} de {pages}",
                use_container_width=True,
            )
            with st.expander("Ver texto extraído del PDF"):
                st.text_area(
                    "Texto OCR/PDF",
                    str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
                    height=220,
                    disabled=True,
                    key=f"{key_prefix}_pdf_text",
                    label_visibility="collapsed",
                )
        except Exception as exc:
            st.warning(f"No se pudo renderizar la vista previa del PDF: {exc}")
            st.text_area(
                "Contenido extraído",
                str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
                height=360,
                disabled=True,
                key=f"{key_prefix}_pdf_fallback_text",
                label_visibility="collapsed",
            )
    else:
        st.text_area(
            "Contenido extraído",
            str(record.get("extracted_text", ""))[:25_000] or "No se extrajo texto.",
            height=360,
            disabled=True,
            key=f"{key_prefix}_text",
            label_visibility="collapsed",
        )
    if path.is_file():
        st.download_button(
            "Descargar archivo original",
            data=path.read_bytes(),
            file_name=Path(str(record.get("filename", path.name))).name,
            key=f"{key_prefix}_download",
            use_container_width=True,
        )


db, catalog, classifier = initialize()
entries = catalog["entries"]
counts = db.counts()

st.markdown(
    """
    <div class="hero">
      <div class="brand-mark">PS</div>
      <div><h1>Clasificador documental PROINSALUD</h1>
      <p>Gestión de TRD/CCD, OCR, revisión humana y organización digital conforme al instructivo IAGED-10.</p></div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<div class="institution-badge">PROINSALUD S.A.<br><span style="font-size:.78rem;font-weight:400">Gestión Documental</span></div>', unsafe_allow_html=True)
    st.subheader("Navegación")
    page = st.radio(
        "Ir a",
        [
            "Inicio",
            "1. Fuentes TRD/CCD",
            "2. Instrucciones de manejo",
            "3. Clasificar archivos",
            "4. Asignación manual",
            "5. Revisión humana",
            "6. Buscar en el catálogo",
            "7. Exportar",
            "Ayuda",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Catálogo activo")
    st.write(f"**{catalog['name']}**")
    st.caption(f"{len(entries):,} códigos · {len(dependency_options(entries))} dependencias")
    st.caption("Motor local: OCR + año + TF‑IDF")


if page == "Inicio":
    st.subheader("Estado del sistema")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Códigos del catálogo", f"{len(entries):,}")
    col2.metric("Archivos procesados", f"{counts['total']:,}")
    col3.metric("Pendientes de revisión", f"{counts['pending']:,}")
    col4.metric("Ejemplos aprendidos", f"{counts['reviewed']:,}")

    st.markdown("### Flujo recomendado")
    st.markdown(
        """
        1. Revise o actualice las **fuentes TRD/CCD**.
        2. Consulte las **instrucciones de manejo** y el instructivo institucional incluido.
        3. Seleccione la dependencia, cargue documentos y ejecute **OCR, detección de año y clasificación**.
        4. Use **asignación manual** cuando desee filtrar un área y buscar por nombre.
        5. Apruebe o corrija el año y el código en **revisión humana** y descargue la tabla PDF/Excel.
        6. Revise la tabla, prepare y descargue el ZIP por año, dependencia, serie y subserie.
        """
    )
    st.info(
        "El puntaje es similitud documental, no una probabilidad jurídica. Las decisiones de archivo deben ser validadas por una persona responsable."
    )

elif page == "1. Fuentes TRD/CCD":
    st.subheader("Instrumentos archivísticos y estructura institucional")
    st.write("Consulte la TRD por área, explore el cuadro de clasificación, visualice el organigrama o administre nuevas versiones.")
    trd_tab, ccd_tab, organigram_tab, admin_tab = st.tabs(
        ["TRD por área", "Cuadro de clasificación", "Organigrama", "Administrar fuentes"]
    )

    with trd_tab:
        dep_options = dependency_options(entries)
        selected_area = st.selectbox(
            "Área / dependencia productora",
            options=[code for code, _ in dep_options],
            format_func=lambda code: next(f"{c} - {name}" for c, name in dep_options if c == code),
            key="trd_area_view",
        )
        area_entries = [entry for entry in entries if str(entry.get("dependency_code")) == selected_area]
        area_search = st.text_input(
            "Buscar dentro de la TRD del área",
            placeholder="Serie, subserie, tipo documental o código",
            key="trd_area_search",
        )
        if area_search:
            needle = area_search.casefold()
            area_entries = [entry for entry in area_entries if needle in str(entry.get("search_text", "")).casefold()]
        metric_1, metric_2, metric_3 = st.columns(3)
        metric_1.metric("Registros TRD", len(area_entries))
        metric_2.metric("Series", len({entry.get("series_code") for entry in area_entries}))
        metric_3.metric("Subseries", sum(bool(entry.get("subseries_code")) for entry in area_entries))
        st.dataframe(entry_table(area_entries), use_container_width=True, hide_index=True, height=430)
        if area_entries:
            detail_code = st.selectbox(
                "Ver procedimiento completo",
                options=[entry["code"] for entry in area_entries],
                format_func=lambda code: next(
                    f"{entry['code']} - {entry.get('subseries_name') or entry.get('series_name', '')}"
                    for entry in area_entries
                    if entry["code"] == code
                ),
                key="trd_area_detail",
            )
            detail_entry = next(entry for entry in area_entries if entry["code"] == detail_code)
            detail_1, detail_2, detail_3 = st.columns(3)
            detail_1.metric("Archivo de gestión", detail_entry.get("retention_management") or "—")
            detail_2.metric("Archivo central", detail_entry.get("retention_central") or "—")
            detail_3.metric("Disposición", " / ".join(detail_entry.get("final_disposition") or []) or "—")
            st.text_area(
                "Procedimiento TRD",
                detail_entry.get("procedure") or "No informado.",
                height=160,
                disabled=True,
                key="trd_procedure_detail",
            )

    with ccd_tab:
        ccd_dependencies = [""] + [code for code, _ in dependency_options(entries)]
        ccd_area = st.selectbox(
            "Filtrar cuadro por dependencia",
            options=ccd_dependencies,
            format_func=lambda code: "Todas las dependencias" if not code else next(
                f"{c} - {name}" for c, name in dependency_options(entries) if c == code
            ),
            key="ccd_area_filter",
        )
        ccd_search = st.text_input(
            "Buscar en el cuadro de clasificación",
            placeholder="Sección, dependencia, serie, subserie o código",
            key="ccd_text_filter",
        )
        ccd_entries = [entry for entry in entries if not ccd_area or str(entry.get("dependency_code")) == ccd_area]
        if ccd_search:
            needle = ccd_search.casefold()
            ccd_entries = [entry for entry in ccd_entries if needle in str(entry.get("search_text", "")).casefold()]
        st.metric("Clasificaciones visibles", len(ccd_entries))
        st.dataframe(hierarchy_table(ccd_entries, include_score=False), use_container_width=True, hide_index=True, height=520)

    with organigram_tab:
        st.markdown("### Estructura orgánica de PROINSALUD")
        st.caption("Documento institucional incluido en el proyecto. Para comprobar actualizaciones consulte también el sitio oficial.")
        if ORGANIGRAM_PATH.exists():
            render_document_preview(
                {
                    "stored_path": str(ORGANIGRAM_PATH),
                    "extension": ".pdf",
                    "filename": "Organigrama PROINSALUD.pdf",
                    "extracted_text": "Estructura orgánica institucional de PROINSALUD S.A.",
                },
                "institutional_organigram",
            )
        else:
            st.warning("No se encontró el archivo local del organigrama.")
        st.link_button(
            "Abrir organigrama en el sitio oficial de PROINSALUD",
            "https://www.proinsalud.co/organigrama.php",
            use_container_width=True,
        )

    with admin_tab:
        st.markdown("### Cargar y activar instrumentos archivísticos")
        st.write(
            "Admite Excel, CSV/TSV y ZIP. Un RAR requiere 7-Zip o UnRAR instalado; el catálogo PROINSALUD ya viene normalizado y activo."
        )
        uploads = st.file_uploader(
            "Seleccione una o varias TRD/CCD",
            type=["xlsx", "xlsm", "xls", "csv", "tsv", "zip", "rar"],
            accept_multiple_files=True,
            key="table_uploads",
        )
        col_a, col_b = st.columns([1, 2])
        catalog_name = col_a.text_input("Nombre de la versión", value="Actualización TRD/CCD")
        process_tables = col_b.button(
            "Analizar tablas cargadas", type="primary", disabled=not uploads, use_container_width=True
        )
        if process_tables:
            with st.spinner("Detectando hojas, encabezados y jerarquías documentales…"):
                build = build_catalog_from_files(uploads)
            st.session_state["catalog_preview"] = {
                "entries": build.entries,
                "errors": build.errors,
                "sources": build.sources,
                "stats": build.stats,
                "trd_rows": build.trd_rows,
                "ccd_rows": build.ccd_rows,
                "name": catalog_name,
            }
        preview = st.session_state.get("catalog_preview")
        if preview:
            stats = preview["stats"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Registros detectados", stats["registros"])
            c2.metric("Dependencias", stats["dependencias"])
            c3.metric("Filas TRD", preview["trd_rows"])
            c4.metric("Filas CCD", preview["ccd_rows"])
            for error in preview["errors"]:
                st.warning(error)
            if preview["entries"]:
                st.dataframe(entry_table(preview["entries"]), use_container_width=True, hide_index=True, height=330)
                if st.button("Activar esta versión de catálogo", type="primary"):
                    db.save_catalog(
                        preview["name"],
                        preview["entries"],
                        {"fuentes": preview["sources"], "estadisticas": preview["stats"]},
                    )
                    get_classifier.clear()
                    del st.session_state["catalog_preview"]
                    st.success("La nueva versión quedó activa.")
                    st.rerun()
        st.divider()
        versions = db.list_catalogs()
        version_labels = {version["id"]: f"#{version['id']} · {version['name']} · {version['created_at'][:10]}" for version in versions}
        selected_version = st.selectbox(
            "Versiones disponibles",
            options=[version["id"] for version in versions],
            format_func=lambda value: version_labels[value],
            index=next((index for index, version in enumerate(versions) if version["is_active"]), 0),
        )
        if st.button("Usar la versión seleccionada", disabled=selected_version == catalog["id"]):
            db.activate_catalog(selected_version)
            get_classifier.clear()
            st.rerun()
        st.download_button(
            "Descargar catálogo normalizado (JSON)",
            data=json.dumps({"metadata": catalog["metadata"], "entries": entries}, ensure_ascii=False, indent=2),
            file_name="catalogo_trd_ccd_normalizado.json",
            mime="application/json",
        )

elif page == "2. Instrucciones de manejo":
    st.subheader("Instrucciones de manejo del clasificador")
    st.write("Recorra el flujo en orden. Cada paso incluye la acción principal y el resultado esperado.")
    instruction_columns = st.columns(4)
    cards = [
        ("1", "Consultar", "Revise TRD, CCD y organigrama antes de clasificar."),
        ("2", "Cargar", "Seleccione dependencia, OCR y documentos o un ZIP."),
        ("3", "Validar", "Confirme año, serie y subserie en revisión humana."),
        ("4", "Exportar", "Genere tabla PDF/Excel y ZIP con las carpetas TRD."),
    ]
    for column, (number, title, description) in zip(instruction_columns, cards):
        with column:
            st.markdown(
                f'<div class="instruction-card"><h3>{number}. {title}</h3><p>{description}</p></div>',
                unsafe_allow_html=True,
            )
    st.write("")
    guide_1, guide_2, guide_3, guide_4 = st.tabs(
        ["Preparar", "Clasificar", "Revisar", "Exportar"]
    )
    with guide_1:
        st.markdown(
            """
            1. Entre en **Fuentes TRD/CCD**.
            2. Seleccione el área para consultar su TRD.
            3. Revise el cuadro de clasificación y el organigrama.
            4. Use **Administrar fuentes** únicamente cuando tenga una versión nueva aprobada.
            """
        )
    with guide_2:
        st.markdown(
            """
            1. Seleccione la dependencia productora.
            2. Mantenga OCR activo para documentos escaneados.
            3. Cargue archivos individuales o un ZIP.
            4. Pulse **Procesar y agregar al listado**.
            5. Use **Seguir cargando otro lote** para acumular más documentos.
            """
        )
    with guide_3:
        st.markdown(
            """
            1. Abra **Revisión humana**.
            2. Compruebe el año detectado y el código sugerido.
            3. Corrija el código cuando sea necesario.
            4. Cambie el estado a Aprobada o Corregida y guarde.
            5. Descargue la tabla PDF o Excel si necesita un soporte de revisión.
            """
        )
    with guide_4:
        st.markdown(
            """
            1. Filtre estados, años y dependencias.
            2. Revise la tabla y la vista previa.
            3. Pulse **Preparar archivo comprimido**.
            4. Descargue el ZIP y verifique la ruta `AÑO / DEPENDENCIA / SERIE / SUBSERIE`.
            """
        )
    st.markdown("### Instructivo institucional")
    if INSTRUCTIONS_PATH.exists():
        render_document_preview(
            {
                "stored_path": str(INSTRUCTIONS_PATH),
                "extension": ".pdf",
                "filename": "Instructivo para la Gestión y Organización de Carpetas Digitales según la TRD.pdf",
                "extracted_text": "Instructivo institucional IAGED-10 para la organización de carpetas digitales.",
            },
            "institutional_instructions",
        )

elif page == "3. Clasificar archivos":
    st.subheader("Clasificación automática de documentos")
    st.write(
        "Seleccione primero la dependencia. Después, el sistema extrae texto y OCR, detecta el año documental y compara el contenido con la TRD."
    )
    dep_options = dependency_options(entries)
    selected_dep = st.selectbox(
        "1. Dependencia para esta carga",
        options=[""] + [code for code, _ in dep_options],
        format_func=lambda code: "Todas las dependencias" if not code else next(
            f"{c} — {name}" for c, name in dep_options if c == code
        ),
    )
    settings_1, settings_2, settings_3 = st.columns(3)
    with settings_1:
        year_mode = st.radio("2. Año documental", ["Detectar automáticamente", "Usar año fijo"], horizontal=False)
        default_year = st.number_input(
            "Año predeterminado",
            min_value=1990,
            max_value=datetime.now().year + 1,
            value=datetime.now().year,
            step=1,
        )
    with settings_2:
        enable_ocr = st.checkbox("Aplicar OCR a PDF escaneados e imágenes", value=True)
        ocr_language = st.selectbox("Idioma OCR", ["spa+eng", "spa", "eng"], index=0)
        max_ocr_pages = st.number_input("Máximo de páginas OCR por PDF", 1, 200, 50)
    with settings_3:
        top_k = st.slider("Alternativas por archivo", min_value=3, max_value=10, value=5)
        st.caption("La dependencia elegida limita las alternativas y mejora la precisión.")
    if "document_uploader_version" not in st.session_state:
        st.session_state["document_uploader_version"] = 0
    uploads = st.file_uploader(
        "3. Cargue documentos o un ZIP",
        type=DOCUMENT_UPLOAD_TYPES,
        accept_multiple_files=True,
        key=f"document_uploads_{st.session_state['document_uploader_version']}",
    )
    load_col_1, load_col_2, load_col_3 = st.columns(3)
    process_uploads = load_col_1.button(
        "Procesar y agregar al listado",
        type="primary",
        disabled=not uploads,
        use_container_width=True,
        key="process_document_uploads",
    )
    continue_loading = load_col_2.button(
        "Seguir cargando otro lote",
        disabled=not st.session_state.get("last_results"),
        use_container_width=True,
        key="continue_document_uploads",
    )
    clear_loading = load_col_3.button(
        "Limpiar archivos y listado",
        use_container_width=True,
        key="clear_document_uploads",
    )
    st.caption(
        "Seguir cargando conserva el listado y limpia el selector. Limpiar reinicia la pantalla, pero no borra el historial guardado en Revisión humana."
    )

    if continue_loading:
        st.session_state["document_uploader_version"] += 1
        st.rerun()

    if clear_loading:
        st.session_state.pop("last_results", None)
        st.session_state["document_uploader_version"] += 1
        st.rerun()

    if process_uploads:
        payloads, expansion_warnings = expand_document_uploads(uploads)
        for warning in expansion_warnings:
            st.warning(warning)
        results = []
        progress = st.progress(0, text="Preparando documentos…")
        for number, payload in enumerate(payloads, start=1):
            progress.progress((number - 1) / max(len(payloads), 1), text=f"Extracción/OCR: {payload.name}")
            extracted = extract_document(
                payload,
                enable_ocr=enable_ocr,
                ocr_language=ocr_language,
                max_ocr_pages=int(max_ocr_pages),
            )
            if year_mode == "Usar año fijo":
                year_result = {
                    "year": str(int(default_year)),
                    "source": "año fijo seleccionado para la carga",
                    "confidence": 1.0,
                    "candidates": {str(int(default_year)): 1},
                }
            else:
                year_result = detect_document_year(
                    payload.name,
                    extracted.text,
                    extracted.metadata,
                    default_year=int(default_year),
                )
            candidates = classifier.classify(payload.name, extracted.text, dependency_code=selected_dep or None, top_k=top_k)
            document_id = db.save_document(payload, extracted)
            classification_id = db.save_classification(
                document_id,
                catalog["id"],
                candidates,
                document_year=year_result["year"],
                year_source=year_result["source"],
                year_confidence=float(year_result["confidence"]),
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
        progress.progress(1.0, text=f"Listo: {len(results)} archivo(s) procesado(s)")
        st.session_state["last_results"] = merge_results_by_sha(
            st.session_state.get("last_results", []),
            results,
        )

    last_results = st.session_state.get("last_results", [])
    if last_results:
        summary = []
        for result in last_results:
            top = result["candidates"][0] if result["candidates"] else {}
            summary.append(
                {
                    "Año": result["year"]["year"],
                    "Archivo": result["filename"],
                    "Código sugerido": top.get("code", "Sin coincidencia"),
                    "Dependencia": top.get("dependency_name", ""),
                    "Serie": top.get("series_name", ""),
                    "Subserie": top.get("subseries_name", ""),
                    "Similitud": top.get("score_percent", 0),
                    "Confianza": top.get("confidence", "Baja"),
                    "OCR": "Sí" if result["extracted"].metadata.get("ocr_performed") or result["extracted"].metadata.get("ocr") else "No",
                }
            )
        st.dataframe(
            pd.DataFrame(summary),
            use_container_width=True,
            hide_index=True,
            column_config={"Similitud": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")},
        )
        for preview_index, result in enumerate(last_results):
            top = result["candidates"][0] if result["candidates"] else {}
            label = f"{result['filename']} — {top.get('code', 'sin coincidencia')}"
            with st.expander(label):
                st.info(
                    f"Año detectado: {result['year']['year']} · origen: {result['year']['source']} · "
                    f"confianza: {result['year']['confidence'] * 100:.0f}%"
                )
                if result["extracted"].warnings:
                    for warning in result["extracted"].warnings:
                        st.warning(warning)
                left, right = st.columns([1, 1])
                with left:
                    st.caption("Alternativas")
                    st.dataframe(entry_table(result["candidates"], include_score=True), use_container_width=True, hide_index=True)
                with right:
                    st.caption("Contenido extraído — vista previa")
                    st.text_area(
                        "Texto",
                        value=result["extracted"].preview or "No se extrajo texto.",
                        height=260,
                        disabled=True,
                        key=preview_widget_key(
                            result["classification_id"], preview_index, result.get("sha256", "")
                        ),
                        label_visibility="collapsed",
                    )

elif page == "4. Asignación manual":
    st.subheader("Asignación manual por área y nombre del documento")
    st.write(
        "Filtre la dependencia, escriba cómo se llama el documento y seleccione la serie o subserie correcta. "
        "En este módulo solo se muestra la jerarquía desde sección y dependencia en adelante."
    )
    dep_options = dependency_options(entries)
    manual_dep = st.selectbox(
        "1. Área / dependencia",
        options=[""] + [code for code, _ in dep_options],
        format_func=lambda code: "Seleccione una dependencia" if not code else next(
            f"{c} - {name}" for c, name in dep_options if c == code
        ),
        key="manual_dependency",
    )
    manual_name = st.text_input(
        "2. Nombre del documento",
        placeholder="Ej.: acta del comité de archivo, conciliación bancaria, contrato de arrendamiento",
        key="manual_document_name",
    )
    manual_description = st.text_area(
        "Descripción adicional opcional",
        placeholder="Puede escribir palabras que aparecen en el documento para mejorar la búsqueda.",
        height=100,
        key="manual_document_description",
    )
    if st.button(
        "Buscar clasificación dentro de la dependencia",
        type="primary",
        disabled=not manual_dep or not manual_name.strip(),
        use_container_width=True,
    ):
        st.session_state["manual_matches"] = classifier.search(
            f"{manual_name} {manual_description}",
            dependency_code=manual_dep,
            top_k=25,
        )
        st.session_state["manual_matches_dependency"] = manual_dep

    manual_matches = st.session_state.get("manual_matches", [])
    if manual_matches and st.session_state.get("manual_matches_dependency") == manual_dep:
        st.markdown("### Clasificaciones encontradas")
        st.dataframe(
            hierarchy_table(manual_matches),
            use_container_width=True,
            hide_index=True,
            column_config={"Similitud": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")},
        )
        selected_manual_code = st.selectbox(
            "3. Clasificación que desea asignar",
            options=[entry["code"] for entry in manual_matches],
            format_func=lambda code: next(
                f"{entry['code']} - {entry.get('subseries_name') or entry.get('series_name', '')}"
                for entry in manual_matches
                if entry["code"] == code
            ),
            key="manual_selected_code",
        )
        manual_year = st.number_input(
            "4. Año de los documentos",
            min_value=1990,
            max_value=datetime.now().year + 1,
            value=datetime.now().year,
            step=1,
            key="manual_year",
        )
        manual_uploads = st.file_uploader(
            "5. Archivos que se ubicarán en esta clasificación",
            type=DOCUMENT_UPLOAD_TYPES,
            accept_multiple_files=True,
            key="manual_document_uploads",
        )
        if st.button(
            "Asignar documentos a la clasificación seleccionada",
            type="primary",
            disabled=not manual_uploads,
            use_container_width=True,
        ):
            payloads, warnings = expand_document_uploads(manual_uploads)
            for warning in warnings:
                st.warning(warning)
            selected_entry = next(entry for entry in manual_matches if entry["code"] == selected_manual_code)
            manual_candidate = dict(selected_entry)
            manual_candidate.update({"score": 1.0, "score_percent": 100.0, "confidence": "Manual"})
            assigned = 0
            for payload in payloads:
                extracted = extract_document(payload, enable_ocr=True, ocr_language="spa+eng", max_ocr_pages=50)
                document_id = db.save_document(payload, extracted)
                classification_id = db.save_classification(
                    document_id,
                    catalog["id"],
                    [manual_candidate],
                    document_year=str(int(manual_year)),
                    year_source="año definido en asignación manual",
                    year_confidence=1.0,
                )
                db.update_review(
                    classification_id,
                    selected_manual_code,
                    "Aprobada",
                    f"Asignación manual: {manual_name}",
                    document_year=int(manual_year),
                )
                assigned += 1
            get_classifier.clear()
            st.success(
                f"{assigned} documento(s) asignado(s) a {selected_manual_code}. "
                "Ya aparecen en Revisión humana y Exportar."
            )
    elif manual_dep and manual_name:
        st.info("Pulse el botón de búsqueda para ver las series y subseries de esta dependencia.")

elif page == "5. Revisión humana":
    st.subheader("Validar, aprobar o corregir sugerencias")
    records = db.list_classifications()
    if not records:
        st.info("Todavía no hay documentos clasificados.")
    else:
        status_filter = st.multiselect(
            "Estado",
            ["Pendiente", "Aprobada", "Corregida", "Descartada"],
            default=["Pendiente", "Aprobada", "Corregida"],
        )
        visible = [r for r in records if r["status"] in status_filter][:1_000]
        codes = [str(e.get("code")) for e in entries]
        display_rows = [
            {
                "id": r["id"],
                "Año": int(r["document_year"] or datetime.now().year),
                "Archivo": r["filename"],
                "Sugerencia": r["suggested_code"],
                "Similitud": round(float(r["suggested_score"]) * 100, 1),
                "Confianza": r["confidence"],
                "Código final": r["final_code"] or r["suggested_code"],
                "Estado": r["status"],
                "Observaciones": r["reviewer_notes"],
            }
            for r in visible
        ]
        edited = st.data_editor(
            pd.DataFrame(display_rows),
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            disabled=["id", "Archivo", "Sugerencia", "Similitud", "Confianza"],
            column_config={
                "id": None,
                "Año": st.column_config.NumberColumn(
                    "Año",
                    min_value=1990,
                    max_value=datetime.now().year + 1,
                    step=1,
                    format="%d",
                    required=True,
                ),
                "Similitud": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                "Código final": st.column_config.SelectboxColumn(options=codes, required=True),
                "Estado": st.column_config.SelectboxColumn(
                    options=["Pendiente", "Aprobada", "Corregida", "Descartada"], required=True
                ),
                "Observaciones": st.column_config.TextColumn(width="large"),
            },
            key="review_editor",
        )
        if st.button("Guardar revisión", type="primary", disabled=edited.empty):
            for row in edited.to_dict(orient="records"):
                status = row["Estado"]
                if row["Código final"] != row["Sugerencia"] and status == "Aprobada":
                    status = "Corregida"
                db.update_review(
                    int(row["id"]),
                    str(row["Código final"]),
                    str(status),
                    str(row["Observaciones"] or ""),
                    document_year=int(row["Año"]),
                )
            get_classifier.clear()
            st.success("Revisión guardada. Las aprobaciones alimentarán las próximas búsquedas.")
            st.rerun()

        if visible:
            review_rows = manifest_rows(visible, entries)
            st.markdown("### Descargar tabla de revisión guardada")
            review_download_1, review_download_2 = st.columns(2)
            review_download_1.download_button(
                "Descargar tabla en Excel XLSX",
                data=to_xlsx_bytes(review_rows),
                file_name="tabla_revision_documental.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="review_download_xlsx",
                use_container_width=True,
            )
            review_download_2.download_button(
                "Descargar tabla imprimible en PDF",
                data=to_pdf_bytes(review_rows, title="Tabla de revisión documental"),
                file_name="tabla_revision_documental.pdf",
                mime="application/pdf",
                key="review_download_pdf",
                use_container_width=True,
            )

        selected_record = st.selectbox(
            "Inspeccionar detalle",
            options=visible,
            format_func=lambda r: f"#{r['id']} · {r['filename']}",
        ) if visible else None
        if selected_record:
            left, right = st.columns(2)
            with left:
                st.caption(f"Vista previa · año {selected_record['document_year']} · {selected_record['year_source']}")
                render_document_preview(selected_record, f"review_{selected_record['id']}")
            with right:
                st.caption("Alternativas calculadas")
                st.dataframe(entry_table(selected_record["candidates"], include_score=True), use_container_width=True, hide_index=True)
                if selected_record["metadata"].get("ocr_performed"):
                    st.success(f"OCR aplicado en páginas: {selected_record['metadata'].get('ocr_pages', [])}")
                elif selected_record["metadata"].get("ocr"):
                    st.success("OCR aplicado a la imagen.")
                for warning in selected_record["warnings"]:
                    st.warning(warning)

elif page == "6. Buscar en el catálogo":
    st.subheader("Búsqueda inteligente en TRD y CCD")
    query = st.text_input(
        "Describa el documento o expediente",
        placeholder="Ej.: contrato de arrendamiento con póliza y acta de liquidación",
    )
    dep_options = dependency_options(entries)
    search_dep = st.selectbox(
        "Dependencia",
        options=[""] + [code for code, _ in dep_options],
        format_func=lambda code: "Todas" if not code else next(f"{c} — {name}" for c, name in dep_options if c == code),
        key="search_dependency",
    )
    number_results = st.slider("Resultados", 5, 50, 15)
    if query:
        matches = classifier.search(query, dependency_code=search_dep or None, top_k=number_results)
        st.dataframe(
            entry_table(matches, include_score=True),
            use_container_width=True,
            hide_index=True,
            column_config={"Similitud": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")},
        )
        if matches:
            selected_code = st.selectbox("Ver ficha completa", [m["code"] for m in matches])
            selected = next(m for m in matches if m["code"] == selected_code)
            c1, c2, c3 = st.columns(3)
            c1.metric("Archivo de gestión", selected.get("retention_management") or "—")
            c2.metric("Archivo central", selected.get("retention_central") or "—")
            c3.metric("Disposición", " / ".join(selected.get("final_disposition") or []) or "—")
            st.write("**Tipos documentales:**", " · ".join(selected.get("document_types") or []) or "No informados")
            st.write("**Procedimiento:**", selected.get("procedure") or "No informado")

elif page == "7. Exportar":
    st.subheader("Revisar tabla y generar carpetas según el instructivo")
    records = db.list_classifications()
    if not records:
        st.info("No hay resultados para exportar.")
    else:
        catalog_by_code = {str(entry.get("code")): entry for entry in entries}
        available_years = sorted({str(r.get("document_year") or "SIN_ANIO") for r in records}, reverse=True)
        record_dependency_codes = sorted(
            {
                str(catalog_by_code.get(str(r.get("final_code") or r.get("suggested_code")), {}).get("dependency_code"))
                for r in records
                if catalog_by_code.get(str(r.get("final_code") or r.get("suggested_code")), {}).get("dependency_code")
            },
            key=lambda code: tuple(int(part) for part in code.split(".")),
        )
        filter_1, filter_2, filter_3 = st.columns(3)
        with filter_1:
            export_statuses = st.multiselect(
                "Estados",
                ["Pendiente", "Aprobada", "Corregida", "Descartada"],
                default=["Pendiente", "Aprobada", "Corregida"],
            )
        with filter_2:
            export_years = st.multiselect("Años", available_years, default=available_years)
        with filter_3:
            export_dependencies = st.multiselect(
                "Dependencias",
                record_dependency_codes,
                default=record_dependency_codes,
                format_func=lambda code: next(
                    (f"{c} - {name}" for c, name in dependency_options(entries) if c == code), code
                ),
            )

        def record_dependency(record: dict) -> str:
            code = str(record.get("final_code") or record.get("suggested_code") or "")
            return str(catalog_by_code.get(code, {}).get("dependency_code", ""))

        selected_records = [
            r
            for r in records
            if r["status"] in export_statuses
            and str(r.get("document_year") or "SIN_ANIO") in export_years
            and (not export_dependencies or record_dependency(r) in export_dependencies)
        ]
        rows = manifest_rows(selected_records, entries)
        st.metric("Documentos en la tabla", len(rows))
        st.caption("Revise esta tabla antes de generar el comprimido. El año y el código final se pueden corregir en Revisión humana.")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=360)
        if selected_records:
            preview_record = st.selectbox(
                "Vista previa del documento antes de exportar",
                selected_records,
                format_func=lambda record: f"{record.get('document_year')} · {record.get('filename')}",
            )
            preview_left, preview_right = st.columns([1.2, 1])
            with preview_left:
                render_document_preview(preview_record, f"export_{preview_record['id']}")
            with preview_right:
                code = str(preview_record.get("final_code") or preview_record.get("suggested_code") or "")
                entry = catalog_by_code.get(code, {})
                st.write(f"**Año:** {preview_record.get('document_year')}")
                st.write(f"**Código final:** {code or 'Sin código'}")
                st.write(f"**Dependencia:** {entry.get('dependency_name', '')}")
                st.write(f"**Serie:** {entry.get('series_name', '')}")
                st.write(f"**Subserie:** {entry.get('subseries_name', '') or 'No aplica'}")
                st.write(f"**Estado:** {preview_record.get('status')}")

        st.markdown("### Descargas de la tabla")
        c1, c2, c3, c4 = st.columns(4)
        c1.download_button(
            "Descargar Excel",
            data=to_xlsx_bytes(rows),
            file_name="manifesto_clasificacion_documental.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=not rows,
        )
        c2.download_button(
            "Descargar CSV",
            data=to_csv_bytes(rows),
            file_name="manifesto_clasificacion_documental.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not rows,
        )
        c3.download_button(
            "Descargar JSON",
            data=to_json_bytes(rows),
            file_name="manifesto_clasificacion_documental.json",
            mime="application/json",
            use_container_width=True,
            disabled=not rows,
        )
        c4.download_button(
            "Descargar PDF imprimible",
            data=to_pdf_bytes(rows),
            file_name="tabla_clasificacion_documental.pdf",
            mime="application/pdf",
            use_container_width=True,
            disabled=not rows,
        )
        include_structure = st.checkbox(
            "Incluir la estructura TRD completa de las dependencias y años seleccionados",
            value=True,
            help="Crea también las carpetas vacías de serie y subserie, como indica el instructivo IAGED-10.",
        )
        st.code(
            "AÑO / CÓDIGO - DEPENDENCIA / CÓDIGO.SERIE - SERIE / CÓDIGO COMPLETO - SUBSERIE / archivo",
            language=None,
        )
        zip_signature_data = {
            "records": [
                [record.get("id"), record.get("updated_at"), record.get("final_code"), record.get("document_year")]
                for record in selected_records
            ],
            "years": export_years,
            "dependencies": export_dependencies,
            "include_structure": include_structure,
        }
        zip_signature = hashlib.sha256(
            json.dumps(zip_signature_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        prepared_zip = st.session_state.get("prepared_export_zip")
        if prepared_zip and prepared_zip.get("signature") != zip_signature:
            st.session_state.pop("prepared_export_zip", None)
            prepared_zip = None

        if st.button(
            "1. Preparar archivo comprimido",
            type="primary",
            use_container_width=True,
            disabled=not rows,
            key="prepare_export_zip",
        ):
            try:
                with st.spinner("Creando carpetas y ubicando cada documento…"):
                    zip_bytes = build_classified_zip(
                        selected_records,
                        entries,
                        include_full_structure=include_structure,
                        years=export_years,
                        dependency_codes=export_dependencies,
                    )
                st.session_state["prepared_export_zip"] = {
                    "signature": zip_signature,
                    "data": zip_bytes,
                    "records": len(selected_records),
                }
                prepared_zip = st.session_state["prepared_export_zip"]
                st.success("El archivo comprimido fue preparado correctamente.")
            except Exception as exc:
                st.session_state.pop("prepared_export_zip", None)
                st.error(f"No se pudo crear el comprimido: {exc}")

        if prepared_zip and prepared_zip.get("signature") == zip_signature:
            size_mb = len(prepared_zip["data"]) / (1024 * 1024)
            st.info(
                f"ZIP listo: {prepared_zip['records']} documento(s), {size_mb:.2f} MB. "
                "Los pendientes también se ubican según su código sugerido."
            )
            st.download_button(
                "2. Descargar ZIP organizado",
                data=prepared_zip["data"],
                file_name="expedientes_clasificados.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
                key="download_prepared_zip",
            )

elif page == "Ayuda":
    st.subheader("Alcance, seguridad y criterios")
    st.markdown(
        """
        - El motor trabaja **sin servicios externos**: construye un índice TF‑IDF con la dependencia, serie, subserie, tipos documentales y procedimiento.
        - El año se detecta ponderando el nombre del archivo, encabezado OCR, contenido y metadatos; puede corregirse manualmente.
        - Las aprobaciones y correcciones se incorporan como ejemplos locales para las búsquedas posteriores.
        - Un puntaje alto significa mayor similitud textual, no validez archivística automática.
        - PDF escaneados e imágenes se procesan con **Tesseract OCR** y PyMuPDF. Sin Tesseract, el nombre del archivo todavía participa en la clasificación.
        - El ZIP sigue el instructivo IAGED-10: `AÑO / DEPENDENCIA / SERIE / SUBSERIE / ARCHIVO`.
        - La tabla puede descargarse en Excel, CSV, JSON y PDF imprimible.
        - En Exportar primero se prepara el ZIP y después se habilita su descarga; los pendientes se ubican con el código sugerido.
        - Los PDF se previsualizan como imágenes renderizadas para evitar incompatibilidades con `st.pdf`.
        - Archivos cifrados, dañados o sin texto deben revisarse manualmente.
        - Los originales permanecen en `runtime/uploads`; la base local está en `runtime/clasificador.sqlite3`.
        - Para producción, proteja el acceso, cifre el disco, haga copias de seguridad y defina perfiles de usuario.
        """
    )
    st.warning("No elimine ni transfiera documentos únicamente por la sugerencia automática. Aplique la TRD vigente y el procedimiento institucional aprobado.")
