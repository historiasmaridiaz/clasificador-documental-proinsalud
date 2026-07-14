from __future__ import annotations

from typing import Any


LIGHT_THEME: dict[str, str] = {
    "bg": "#F6F8FB",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF2F6",
    "text": "#173F67",
    "muted": "#5F6F7E",
    "line": "#DCE3EA",
    "blue": "#173F67",
    "orange": "#D97812",
    "purple": "#6846D9",
    "purple_hover": "#5635C5",
    "input": "#FFFFFF",
    "control": "#243B73",
    "control_hover": "#1B2F5D",
    "control_disabled": "#7785A5",
    "menu_hover": "#E8EAF7",
}

DARK_THEME: dict[str, str] = {
    "bg": "#0E151D",
    "surface": "#17212B",
    "surface_alt": "#202D39",
    "text": "#EAF2F8",
    "muted": "#A9BAC8",
    "line": "#344554",
    "blue": "#8FC8F2",
    "orange": "#FFAA4D",
    "purple": "#8B6CF6",
    "purple_hover": "#7657E6",
    "input": "#111B24",
    "control": "#302C68",
    "control_hover": "#443B8C",
    "control_disabled": "#4C5268",
    "menu_hover": "#293947",
}


def _variables(theme: dict[str, Any], *, dark_mode: bool) -> str:
    values = {
        "BG": theme["bg"],
        "SURFACE": theme["surface"],
        "SURFACE_ALT": theme["surface_alt"],
        "TEXT": theme["text"],
        "MUTED": theme["muted"],
        "LINE": theme["line"],
        "BLUE": theme["blue"],
        "ORANGE": theme["orange"],
        "PURPLE": theme["purple"],
        "PURPLE_HOVER": theme["purple_hover"],
        "INPUT": theme["input"],
        "CONTROL": theme["control"],
        "CONTROL_HOVER": theme["control_hover"],
        "CONTROL_DISABLED": theme["control_disabled"],
        "MENU_HOVER": theme["menu_hover"],
        "COLOR_SCHEME": "dark" if dark_mode else "light",
    }
    return ";".join(f"--pro-{key.lower().replace('_', '-')}:{value}" for key, value in values.items())


def build_theme_css(*, dark_mode: bool = False, focus_mode: bool = False) -> str:
    """Construye el tema visual con controles de alto contraste.

    Streamlit renderiza botones, popovers y selectores con componentes distintos.
    Por eso se cubren tanto sus ``data-testid`` como los componentes BaseWeb,
    evitando controles blancos o texto invisible en cualquiera de los dos modos.
    """

    theme = DARK_THEME if dark_mode else LIGHT_THEME
    css = f"""
:root {{{_variables(theme, dark_mode=dark_mode)};}}
html {{color-scheme:var(--pro-color-scheme);}}
.block-container {{padding-top:1rem;padding-bottom:2.4rem;max-width:1460px;}}
[data-testid="stAppViewContainer"], .stApp {{background:var(--pro-bg);color:var(--pro-text);}}
[data-testid="stHeader"] {{background:color-mix(in srgb, var(--pro-bg) 92%, transparent);}}
[data-testid="stSidebar"] {{background:var(--pro-surface);border-right:1px solid var(--pro-line);}}
[data-testid="stSidebar"] * {{color:var(--pro-text);}}
[data-testid="stMetric"] {{background:var(--pro-surface);border:1px solid var(--pro-line);padding:.8rem;border-radius:.65rem;box-shadow:none;}}
.hero {{padding:1rem 1.15rem;border-radius:.75rem;background:var(--pro-surface);color:var(--pro-text);margin-bottom:.8rem;border:1px solid var(--pro-line);border-left:5px solid var(--pro-orange);}}
.hero h1 {{font-size:1.55rem;margin:0 0 .15rem 0;color:var(--pro-text)!important;}}.hero p{{margin:0;color:var(--pro-muted)!important;}}
.module-card {{height:100%;padding:.9rem;border-radius:.65rem;background:var(--pro-surface);border:1px solid var(--pro-line);box-shadow:none;}}
.module-card h3 {{color:var(--pro-text)!important;margin:.15rem 0 .35rem;font-size:1rem;}}.module-card p{{margin:0;color:var(--pro-muted)!important;font-size:.9rem;}}
.institution-badge {{padding:.7rem .8rem;border-radius:.6rem;background:#173F67;color:white;text-align:left;font-weight:750;}}
.institution-badge * {{color:white!important;}}
.step-badge {{display:inline-block;color:var(--pro-orange);font-size:.75rem;font-weight:800;letter-spacing:.04em;}}
.soft-panel {{padding:.9rem;border:1px solid var(--pro-line);border-radius:.65rem;background:var(--pro-surface);}}
.workflow {{display:flex;gap:.35rem;align-items:center;margin:.25rem 0 1rem;flex-wrap:wrap;}}
.workflow span {{padding:.32rem .58rem;border:1px solid var(--pro-line);background:var(--pro-surface);border-radius:.45rem;color:var(--pro-muted);font-size:.82rem;}}
.workflow span.active {{background:#173F67;color:white;border-color:#173F67;font-weight:700;}}

/* Encabezados y textos: evita títulos oscuros sobre el fondo nocturno. */
h1,h2,h3,h4,h5,h6,label,p,.stMarkdown,[data-testid="stHeadingWithActionElements"] * {{color:var(--pro-text);}}
[data-testid="stCaptionContainer"] p,.stCaption,small {{color:var(--pro-muted)!important;}}
hr {{border-color:var(--pro-line)!important;}}
.small-note {{font-size:.84rem;color:var(--pro-muted);}}
.review-toolbar {{padding:.65rem .75rem;background:var(--pro-surface);border:1px solid var(--pro-line);border-radius:.6rem;margin-bottom:.65rem;}}
.focus-title {{margin:0;color:var(--pro-text);font-size:1.2rem;font-weight:750;}}

/* Pestañas: se mantienen diferenciadas de los botones de acción. */
div[data-baseweb="tab-list"] {{gap:.25rem;}}
button[data-baseweb="tab"] {{background:var(--pro-surface-alt)!important;border-radius:.45rem;padding:.5rem .75rem;color:var(--pro-text)!important;}}
button[data-baseweb="tab"] * {{color:var(--pro-text)!important;}}
button[data-baseweb="tab"][aria-selected="true"] {{background:var(--pro-blue)!important;color:#FFFFFF!important;}}
button[data-baseweb="tab"][aria-selected="true"] * {{color:#FFFFFF!important;}}

/* Todos los botones estándar, descargas, enlaces y el botón de popover Columnas. */
.stButton > button,
.stDownloadButton > button,
button[data-testid^="stBaseButton-"],
[data-testid="stPopover"] > button,
[data-testid="stPopover"] button,
[data-testid="stLinkButton"] a,
a[data-testid^="stBaseLinkButton-"] {{
  background:var(--pro-control)!important;
  border:1px solid var(--pro-control)!important;
  border-radius:.5rem!important;
  color:#FFFFFF!important;
  font-weight:700!important;
  transition:background .15s ease,border-color .15s ease,transform .05s ease;
}}
.stButton > button *,
.stDownloadButton > button *,
button[data-testid^="stBaseButton-"] *,
[data-testid="stPopover"] button *,
[data-testid="stLinkButton"] a *,
a[data-testid^="stBaseLinkButton-"] * {{color:#FFFFFF!important;fill:#FFFFFF!important;}}
.stButton > button:hover,
.stDownloadButton > button:hover,
button[data-testid^="stBaseButton-"]:hover,
[data-testid="stPopover"] button:hover,
[data-testid="stLinkButton"] a:hover,
a[data-testid^="stBaseLinkButton-"]:hover {{background:var(--pro-control-hover)!important;border-color:var(--pro-control-hover)!important;color:#FFFFFF!important;}}
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {{background:var(--pro-purple)!important;border-color:var(--pro-purple)!important;color:#FFFFFF!important;}}
.stButton > button[kind="primary"] *,
.stDownloadButton > button[kind="primary"] *,
button[data-testid="stBaseButton-primary"] * {{color:#FFFFFF!important;fill:#FFFFFF!important;}}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {{background:var(--pro-purple-hover)!important;border-color:var(--pro-purple-hover)!important;color:#FFFFFF!important;}}
.stButton > button:disabled,
.stDownloadButton > button:disabled,
button[data-testid^="stBaseButton-"]:disabled,
[data-testid="stPopover"] button:disabled {{background:var(--pro-control-disabled)!important;border-color:var(--pro-control-disabled)!important;color:#FFFFFF!important;opacity:.78!important;}}
.stButton > button:disabled *,
.stDownloadButton > button:disabled *,
button[data-testid^="stBaseButton-"]:disabled *,
[data-testid="stPopover"] button:disabled * {{color:#FFFFFF!important;fill:#FFFFFF!important;}}
.stButton > button:active,.stDownloadButton > button:active {{transform:translateY(1px);}}

/* Selectores y multiselectores: nunca quedan blancos en modo nocturno. */
div[data-baseweb="select"] > div,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {{
  background:var(--pro-control)!important;
  border-color:var(--pro-control)!important;
  color:#FFFFFF!important;
}}
div[data-baseweb="select"] > div *,
[data-testid="stSelectbox"] div[data-baseweb="select"] *,
[data-testid="stMultiSelect"] div[data-baseweb="select"] * {{color:#FFFFFF!important;fill:#FFFFFF!important;}}
div[data-baseweb="select"] > div:hover,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div:hover {{background:var(--pro-control-hover)!important;border-color:var(--pro-control-hover)!important;}}
div[data-baseweb="select"][aria-disabled="true"] > div,
[data-testid="stSelectbox"] div[data-baseweb="select"][aria-disabled="true"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"][aria-disabled="true"] > div {{background:var(--pro-control-disabled)!important;border-color:var(--pro-control-disabled)!important;opacity:.82;}}
div[data-baseweb="select"] svg,
[data-testid="stSelectbox"] svg,
[data-testid="stMultiSelect"] svg {{fill:#FFFFFF!important;color:#FFFFFF!important;}}

/* Campos de texto y numéricos conservan el fondo del tema. */
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div,
[data-testid="stNumberInput"] > div > div {{background:var(--pro-input)!important;color:var(--pro-text)!important;border-color:var(--pro-line)!important;}}
input,textarea {{color:var(--pro-text)!important;}}

/* Menús desplegables y popovers abiertos. */
[data-baseweb="popover"],
[data-testid="stPopoverBody"],
[data-baseweb="menu"],
ul[role="listbox"] {{background:var(--pro-surface)!important;border-color:var(--pro-line)!important;color:var(--pro-text)!important;}}
[role="option"] {{background:var(--pro-surface)!important;color:var(--pro-text)!important;}}
[role="option"] * {{color:var(--pro-text)!important;}}
[role="option"]:hover {{background:var(--pro-menu-hover)!important;}}
[role="option"][aria-selected="true"] {{background:var(--pro-purple)!important;color:#FFFFFF!important;}}
[role="option"][aria-selected="true"] * {{color:#FFFFFF!important;}}
[data-testid="stPopoverBody"] label,
[data-testid="stPopoverBody"] span,
[data-testid="stPopoverBody"] p {{color:var(--pro-text)!important;}}

/* Carga de archivos, expansores, alertas y tabla. */
[data-testid="stFileUploaderDropzone"] {{background:var(--pro-surface-alt)!important;border-color:var(--pro-line)!important;}}
[data-testid="stFileUploaderDropzone"] * {{color:var(--pro-text)!important;}}
[data-testid="stExpander"] details {{background:var(--pro-surface)!important;border-color:var(--pro-line)!important;}}
[data-testid="stDataFrame"] {{
  border:1px solid var(--pro-line);border-radius:.55rem;overflow:hidden;background:#F7FAFD;
  /* Glide Data Grid se mantiene deliberadamente claro, incluso en modo nocturno,
     para que el texto, las casillas y los editores internos siempre tengan contraste. */
  --gdg-accent-color:#6846D9!important;
  --gdg-accent-fg:#FFFFFF!important;
  --gdg-accent-light:#E9E3FF!important;
  --gdg-text-dark:#12375F!important;
  --gdg-text-medium:#365878!important;
  --gdg-text-light:#607A92!important;
  --gdg-text-header:#12375F!important;
  --gdg-text-group-header:#12375F!important;
  --gdg-text-header-selected:#FFFFFF!important;
  --gdg-bg-cell:#F7FAFD!important;
  --gdg-bg-cell-medium:#EDF3F8!important;
  --gdg-bg-header:#E7EEF6!important;
  --gdg-bg-header-has-focus:#D9E5F1!important;
  --gdg-bg-header-hovered:#DDE8F3!important;
  --gdg-bg-group-header:#E7EEF6!important;
  --gdg-bg-group-header-hovered:#DDE8F3!important;
  --gdg-bg-bubble:#E7EEF6!important;
  --gdg-bg-bubble-selected:#6846D9!important;
  --gdg-border-color:#B7C7D6!important;
  --gdg-horizontal-border-color:#D4DEE8!important;
  --gdg-link-color:#173F67!important;
}}

/* Editor emergente de celdas (texto, número y listas desplegables de st.data_editor). */
.gdg-style,
[class*="gdg-"][class*="gdg-style"] {{
  --gdg-accent-color:#6846D9!important;
  --gdg-accent-fg:#FFFFFF!important;
  --gdg-accent-light:#E9E3FF!important;
  --gdg-text-dark:#12375F!important;
  --gdg-text-medium:#365878!important;
  --gdg-text-light:#607A92!important;
  --gdg-bg-cell:#FFFFFF!important;
  --gdg-bg-cell-medium:#EDF3F8!important;
  --gdg-bg-header:#E7EEF6!important;
  --gdg-border-color:#9EB2C4!important;
  background:#FFFFFF!important;
  color:#12375F!important;
  color-scheme:light!important;
}}
.gdg-style input,
.gdg-style textarea,
.gdg-style .gdg-input,
.gdg-style .glide-select,
.gdg-style .glide-select > div {{
  background:#FFFFFF!important;
  color:#12375F!important;
  -webkit-text-fill-color:#12375F!important;
  opacity:1!important;
}}
.gdg-style .glide-select svg {{color:#12375F!important;fill:#12375F!important;}}
.gdg-style [role="option"] {{background:#FFFFFF!important;color:#12375F!important;}}
.gdg-style [role="option"] * {{color:#12375F!important;-webkit-text-fill-color:#12375F!important;}}
.gdg-style [role="option"]:hover {{background:#E9E3FF!important;}}
.gdg-style [role="option"][aria-selected="true"] {{background:#6846D9!important;color:#FFFFFF!important;}}
.gdg-style [role="option"][aria-selected="true"] * {{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;}}

/* Portales de react-select usados por las listas dentro de la tabla. */
body > div[id*="portal"] [role="listbox"],
body > div[class*="portal"] [role="listbox"] {{background:#FFFFFF!important;border:1px solid #9EB2C4!important;}}
body > div[id*="portal"] [role="option"],
body > div[class*="portal"] [role="option"] {{background:#FFFFFF!important;color:#12375F!important;-webkit-text-fill-color:#12375F!important;}}
body > div[id*="portal"] [role="option"]:hover,
body > div[class*="portal"] [role="option"]:hover {{background:#E9E3FF!important;}}
"""
    if focus_mode:
        css += """
[data-testid="stSidebar"],[data-testid="stHeader"],[data-testid="stToolbar"],.hero,.workflow {display:none!important;}
[data-testid="stAppViewContainer"] > .main {margin-left:0!important;}
.block-container {max-width:none!important;width:100%!important;padding:.7rem 1rem 1.2rem!important;}
[data-testid="stDataFrame"] {min-height:64vh;}
"""
    return css
