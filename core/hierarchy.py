from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable


NO_CODE_PREFIXES = (
    "serie sin codigo",
    "subserie sin codigo",
    "otros otras series",
    "clasificacion temporal",
)


def normalize_archival_label(value: Any) -> str:
    """Normaliza denominaciones archivísticas para compararlas sin crear duplicados."""
    text = str(value or "").replace("\xa0", " ").lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"\b(?:serie|subserie)\s+sin\s+codigo\s*[-:]*\s*", " ", text)
    text = re.sub(r"\botros?\s*/?\s*otras?\s+series?\b", " ", text)
    text = re.sub(r"\bclasificacion\s+temporal\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in normalize_archival_label(value).split() if len(token) >= 3}


def label_similarity(left: Any, right: Any) -> float:
    a = normalize_archival_label(left)
    b = normalize_archival_label(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    overlap = len(a_tokens & b_tokens) / max(1, len(a_tokens | b_tokens))
    containment = max(
        len(a_tokens & b_tokens) / max(1, len(a_tokens)),
        len(a_tokens & b_tokens) / max(1, len(b_tokens)),
    )
    sequence = SequenceMatcher(None, a, b).ratio()
    return max(overlap, containment * 0.92, sequence * 0.82)


def _entry_context(entry: dict[str, Any]) -> str:
    document_types = entry.get("document_types") or []
    if isinstance(document_types, str):
        document_types = [document_types]
    return " ".join(
        [
            str(entry.get("series_name") or ""),
            str(entry.get("subseries_name") or ""),
            " ".join(str(value) for value in document_types),
            str(entry.get("procedure") or "")[:2_000],
        ]
    )


def _query_similarity(query: str, entry: dict[str, Any]) -> float:
    query_norm = normalize_archival_label(query)
    if not query_norm:
        return 0.0
    context = _entry_context(entry)
    context_norm = normalize_archival_label(context)
    query_tokens = set(query_norm.split())
    context_tokens = set(context_norm.split())
    token_score = len(query_tokens & context_tokens) / max(1, len(context_tokens))
    subseries_score = label_similarity(query_norm, entry.get("subseries_name", ""))
    type_scores = [label_similarity(query_norm, value) for value in (entry.get("document_types") or [])]
    return max(token_score, subseries_score, max(type_scores, default=0.0))


def official_equivalent(
    entries: Iterable[dict[str, Any]],
    dependency_code: str,
    series_name: str,
    subseries_name: str = "",
    *,
    document_query: str = "",
    allow_series_only: bool = True,
) -> dict[str, Any] | None:
    """Busca la fila o la serie oficial equivalente a una denominación sin código.

    Si la serie existe en la TRD pero la subserie no puede determinarse con seguridad,
    devuelve una entrada de nivel serie. De esta manera, la exportación reutiliza la
    carpeta codificada existente en lugar de crear otra carpeta ``SERIE SIN CÓDIGO``.
    """

    dep = str(dependency_code or "").strip()
    target_series = normalize_archival_label(series_name)
    target_subseries = normalize_archival_label(subseries_name)
    if not dep or not target_series:
        return None

    candidates = [
        dict(entry)
        for entry in entries
        if str(entry.get("dependency_code") or "").strip() == dep
        and normalize_archival_label(entry.get("series_name")) == target_series
    ]
    if not candidates:
        # Respaldo conservador para variaciones menores de plural, guiones o OCR.
        fuzzy = [
            (label_similarity(series_name, entry.get("series_name")), dict(entry))
            for entry in entries
            if str(entry.get("dependency_code") or "").strip() == dep
        ]
        fuzzy.sort(key=lambda item: item[0], reverse=True)
        if not fuzzy or fuzzy[0][0] < 0.93:
            return None
        best_score = fuzzy[0][0]
        candidates = [entry for score, entry in fuzzy if score >= best_score - 0.01]
        target_series = normalize_archival_label(candidates[0].get("series_name"))
        candidates = [
            entry for entry in candidates
            if normalize_archival_label(entry.get("series_name")) == target_series
        ]

    if target_subseries:
        exact_subseries = [
            entry
            for entry in candidates
            if normalize_archival_label(entry.get("subseries_name")) == target_subseries
        ]
        if len(exact_subseries) == 1:
            result = dict(exact_subseries[0])
            result.update({
                "canonical_match": "subseries",
                "is_other": False,
                "is_banter": False,
                "source": "TRD PROINSALUD — equivalencia exacta",
            })
            return result

        fuzzy_subseries = sorted(
            (
                label_similarity(subseries_name, entry.get("subseries_name")),
                entry,
            )
            for entry in candidates
            if entry.get("subseries_name")
        )
        fuzzy_subseries.sort(key=lambda item: item[0], reverse=True)
        if fuzzy_subseries and fuzzy_subseries[0][0] >= 0.94:
            result = dict(fuzzy_subseries[0][1])
            result.update({
                "canonical_match": "subseries",
                "is_other": False,
                "is_banter": False,
                "source": "TRD PROINSALUD — equivalencia normalizada",
            })
            return result

    # Si no se indicó subserie, intenta determinarla solo cuando la evidencia es fuerte.
    if document_query and len(candidates) > 1:
        ranked = sorted(
            ((_query_similarity(document_query, entry), entry) for entry in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        top_score = ranked[0][0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score >= 0.72 and top_score - second_score >= 0.10:
            result = dict(ranked[0][1])
            result.update({
                "canonical_match": "subseries_by_content",
                "is_other": False,
                "is_banter": False,
                "source": "TRD PROINSALUD — equivalencia por contenido",
            })
            return result

    if not allow_series_only:
        return None

    representative = dict(candidates[0])
    series_code = str(representative.get("series_code") or "").strip()
    series_full_code = ".".join(value for value in [dep, series_code] if value)
    document_types: list[str] = []
    seen: set[str] = set()
    for entry in candidates:
        values = entry.get("document_types") or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            key = normalize_archival_label(value)
            if key and key not in seen:
                seen.add(key)
                document_types.append(str(value))

    representative.update(
        {
            "code": series_full_code,
            "series_code": series_code,
            "series_name": str(representative.get("series_name") or series_name),
            "subseries_code": "",
            "subseries_name": "",
            "document_types": document_types,
            "is_other": False,
            "is_banter": False,
            "source": "TRD PROINSALUD — equivalencia de serie",
            "canonical_match": "series",
        }
    )
    return representative


def canonicalize_custom_entry(
    entry: dict[str, Any],
    entries: Iterable[dict[str, Any]],
    *,
    filename: str = "",
    extracted_text: str = "",
) -> dict[str, Any]:
    """Convierte una clasificación BANTER/manual en TRD cuando ya existe equivalencia."""
    if not entry or not entry.get("is_other"):
        return dict(entry or {})
    query = f"{filename} {str(extracted_text or '')[:20_000]}".strip()
    equivalent = official_equivalent(
        entries,
        str(entry.get("dependency_code") or ""),
        str(entry.get("series_name") or ""),
        str(entry.get("subseries_name") or ""),
        document_query=query,
        allow_series_only=True,
    )
    return equivalent or dict(entry)
