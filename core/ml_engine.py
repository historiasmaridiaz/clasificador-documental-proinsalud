from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Iterable

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer


MODEL_VERSION = "PROINSALUD-HYBRID-5"

SPANISH_STOP_WORDS = {
    "a", "al", "algo", "ante", "bajo", "cada", "como", "con", "contra", "cual", "cuando",
    "de", "del", "desde", "donde", "dos", "el", "ella", "ellos", "en", "entre", "era", "es",
    "esa", "ese", "esta", "este", "fue", "ha", "hasta", "la", "las", "lo", "los", "mas", "muy",
    "no", "o", "para", "pero", "por", "que", "se", "ser", "si", "sin", "sobre", "son", "su",
    "sus", "tambien", "todo", "un", "una", "uno", "y", "ya",
}

DOCUMENT_KINDS = {
    "acta": ("acta", "actas"),
    "informe": ("informe", "informes"),
    "contrato": ("contrato", "contratos", "convenio", "convenios"),
    "resolucion": ("resolucion", "resoluciones"),
    "prestamo documental": ("prestamo", "prestamos", "devolucion de documentos"),
    "prueba clinica": ("prueba clinica", "pruebas clinicas", "prueba rapida", "pruebas rapidas"),
    "historia clinica": ("historia clinica", "historias clinicas"),
    "inventario": ("inventario", "inventarios"),
    "instructivo": ("instructivo", "instructivos"),
    "registro": ("registro", "registros"),
    "certificado": ("certificado", "certificados", "certificacion", "certificaciones"),
    "plan": ("plan", "planes"),
    "programa": ("programa", "programas"),
    "manual": ("manual", "manuales"),
    "solicitud": ("solicitud", "solicitudes"),
    "comprobante": ("comprobante", "comprobantes"),
    "factura": ("factura", "facturas"),
    "formato": ("formato", "formatos", "formulario", "formularios"),
    "proceso": ("proceso", "procesos"),
    "expediente": ("expediente", "expedientes"),
}

PAGE_MARKER = re.compile(r"(?im)^\s*={2,}\s*p[aá]gina\s+\d+\s*={2,}\s*$")


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9.\-_/\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Equivalencias institucionales frecuentes. Se agregan, no sustituyen, para
    # conservar el sentido del OCR y mejorar la comparación semántica.
    replacements = (
        (r"\bcomite\s+de\s+archivo\s+clinico\b", "comite de archivo clinico comite de historias clinicas"),
        (r"\barchivo\s+clinico\b", "archivo clinico historias clinicas"),
        (r"\bhistorial\s+clinico\b", "historia clinica"),
        (r"\btabla[s]?\s+documentales\b", "tablas de retencion documental"),
    )
    for pattern, expanded in replacements:
        text = re.sub(pattern, expanded, text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" |\t")
        if not line or PAGE_MARKER.match(line):
            continue
        lines.append(line)
    return lines


def _title_zone(filename: str, text: str, max_chars: int = 3_200) -> str:
    """Extrae el nombre, encabezados y primeras líneas; evita que una mención aislada domine."""
    lines = _clean_lines(text)
    first_lines = lines[:36]
    heading_lines: list[str] = []
    for line in first_lines:
        letters = [character for character in line if character.isalpha()]
        upper_ratio = sum(character.isupper() for character in letters) / max(1, len(letters))
        normalized = normalize_text(line)
        has_kind = any(alias in normalized for aliases in DOCUMENT_KINDS.values() for alias in aliases)
        if len(line) <= 180 and (upper_ratio >= 0.55 or has_kind):
            heading_lines.append(line)
    ordered = [filename, *heading_lines[:14], *first_lines[:18]]
    return "\n".join(ordered)[:max_chars]


def _primary_heading(filename: str, text: str) -> str:
    lines = _clean_lines(text)[:24]
    chosen = ""
    for line in lines:
        normalized = normalize_text(line)
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for aliases in DOCUMENT_KINDS.values() for alias in aliases):
            chosen = line
            break
    if not chosen and lines:
        chosen = lines[0]
    chosen = re.split(r"(?<=[.!?])\s+", chosen, maxsplit=1)[0]
    return f"{filename} {chosen[:260]}".strip()


def _stem_token(token: str) -> str:
    value = token
    for suffix in ("ciones", "cion", "idades", "idad", "amientos", "amiento"):
        if value.endswith(suffix) and len(value) > len(suffix) + 3:
            value = value[: -len(suffix)]
            break
    if value.endswith("es") and len(value) > 5:
        value = value[:-2]
    elif value.endswith("s") and len(value) > 4:
        value = value[:-1]
    return value


def _split_chunks(text: str, max_chunks: int = 18, chunk_chars: int = 2_400) -> list[str]:
    raw = str(text or "")
    pages = [part.strip() for part in PAGE_MARKER.split(raw) if part.strip()]
    if len(pages) <= 1:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=[.!?])\s{2,}", raw) if part.strip()]
        pages = []
        current = ""
        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 1 > chunk_chars and current:
                pages.append(current)
                current = paragraph
            else:
                current = f"{current}\n{paragraph}".strip()
        if current:
            pages.append(current)
    chunks: list[str] = []
    for page in pages:
        if len(page) <= chunk_chars:
            chunks.append(page)
            continue
        for start in range(0, len(page), chunk_chars):
            chunk = page[start : start + chunk_chars]
            if chunk.strip():
                chunks.append(chunk)
    return chunks[:max_chunks]


def _entry_identity_text(entry: dict[str, Any]) -> str:
    dependency = str(entry.get("dependency_name", ""))
    series = str(entry.get("series_name", ""))
    subseries = str(entry.get("subseries_name", ""))
    document_types = entry.get("document_types") or []
    if isinstance(document_types, str):
        document_types = [document_types]
    types_text = " ".join(str(value) for value in document_types)
    return normalize_text(
        " ".join(
            [
                str(entry.get("code", "")),
                str(entry.get("dependency_code", "")),
                dependency,
                series,
                series,
                series,
                subseries,
                subseries,
                subseries,
                subseries,
                types_text,
                types_text,
                types_text,
            ]
        )
    )


def _entry_context_text(entry: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(entry.get("series_name", "")),
                str(entry.get("subseries_name", "")),
                str(entry.get("procedure", ""))[:5_000],
            ]
        )
    )


def _tokens(value: Any) -> set[str]:
    return {
        _stem_token(token)
        for token in re.findall(r"[a-z0-9]{3,}", normalize_text(value))
        if token not in SPANISH_STOP_WORDS
    }


def _coverage(query_tokens: set[str], label: Any) -> float:
    label_tokens = _tokens(label)
    if not label_tokens:
        return 0.0
    return len(query_tokens & label_tokens) / len(label_tokens)


def _detect_kind(value: str) -> str:
    normalized = normalize_text(value)
    best_kind = ""
    best_position = math.inf
    for kind, aliases in DOCUMENT_KINDS.items():
        for alias in aliases:
            match = re.search(rf"\b{re.escape(alias)}\b", normalized)
            if match and match.start() < best_position:
                best_kind = kind
                best_position = match.start()
    return best_kind


def _entry_kinds(entry: dict[str, Any]) -> set[str]:
    document_types = entry.get("document_types") or []
    if isinstance(document_types, str):
        document_types = [document_types]
    text = " ".join(
        [
            str(entry.get("series_name", "")),
            str(entry.get("subseries_name", "")),
            *[str(value) for value in document_types],
        ]
    )
    normalized = normalize_text(text)
    kinds: set[str] = set()
    for kind, aliases in DOCUMENT_KINDS.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            kinds.add(kind)
    return kinds


def _intent_flags(value: Any) -> set[str]:
    """Detecta conceptos que no deben confundirse por similitud ortográfica del OCR."""

    normalized = normalize_text(value)
    tokens = _tokens(normalized)
    flags: set[str] = set()
    if "prestamo" in tokens or "devolucion" in tokens:
        flags.add("prestamo")
    if "prueba" in tokens or "examen" in tokens:
        flags.add("prueba")
    if "historia" in tokens and "clinica" in tokens:
        flags.add("historia_clinica")
    if "registro" in tokens or "control" in tokens:
        flags.add("registro_control")
    if "resultado" in tokens or "reporte" in tokens:
        flags.add("resultado")
    return flags


def _entry_intent_flags(entry: dict[str, Any]) -> set[str]:
    document_types = entry.get("document_types") or []
    if isinstance(document_types, str):
        document_types = [document_types]
    return _intent_flags(
        " ".join(
            [
                str(entry.get("series_name") or ""),
                str(entry.get("subseries_name") or ""),
                *[str(value) for value in document_types],
            ]
        )
    )


class DocumentClassifier:
    """Clasificador híbrido local, explicable y sin API de pago.

    Combina similitud léxica, caracteres, análisis semántico latente, encabezado,
    contenido completo, consenso por páginas/bloques y ejemplos corregidos por el
    usuario. ``score`` es una probabilidad estimada relativa entre alternativas;
    no reemplaza la validación archivística.
    """

    def __init__(
        self,
        entries: Iterable[dict[str, Any]],
        learned_examples: Iterable[dict[str, Any]] | None = None,
    ) -> None:
        self.entries = [dict(entry) for entry in entries]
        if not self.entries:
            raise ValueError("El catálogo no contiene registros para entrenar el índice.")

        examples_by_code: dict[str, list[str]] = defaultdict(list)
        for example in learned_examples or []:
            code = str(example.get("code", ""))
            text = normalize_text(example.get("text", ""))[:20_000]
            if code and text:
                examples_by_code[code].append(text)

        self.identity_texts: list[str] = []
        self.context_texts: list[str] = []
        self.training_texts: list[str] = []
        self.entry_kinds: list[set[str]] = []
        self.entry_intents: list[set[str]] = []
        for entry in self.entries:
            identity = _entry_identity_text(entry)
            context = _entry_context_text(entry)
            examples = " ".join(examples_by_code.get(str(entry.get("code")), [])[-12:])
            self.identity_texts.append(identity)
            self.context_texts.append(context)
            self.training_texts.append(f"{identity} {context} {examples} {examples}".strip())
            self.entry_kinds.append(_entry_kinds(entry))
            self.entry_intents.append(_entry_intent_flags(entry))

        self.word_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 3),
            min_df=1,
            max_df=1.0,
            max_features=95_000,
            sublinear_tf=True,
            stop_words=list(SPANISH_STOP_WORDS),
            token_pattern=r"(?u)\b[\w.-]{2,}\b",
        )
        self.char_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 6),
            min_df=1,
            max_features=110_000,
            sublinear_tf=True,
        )
        self.word_matrix = self.word_vectorizer.fit_transform(self.training_texts)
        self.char_matrix = self.char_vectorizer.fit_transform(self.training_texts)

        max_components = min(
            112,
            max(1, self.word_matrix.shape[0] - 1),
            max(1, self.word_matrix.shape[1] - 1),
        )
        self.semantic_model = None
        self.semantic_matrix = None
        if max_components >= 2:
            self.semantic_model = make_pipeline(
                TruncatedSVD(n_components=max_components, random_state=42),
                Normalizer(copy=False),
            )
            self.semantic_matrix = self.semantic_model.fit_transform(self.word_matrix)

    def _similarity(self, values: list[str]) -> np.ndarray:
        normalized = [normalize_text(value) for value in values]
        word_query = self.word_vectorizer.transform(normalized)
        char_query = self.char_vectorizer.transform(normalized)
        word_scores = cosine_similarity(word_query, self.word_matrix)
        char_scores = cosine_similarity(char_query, self.char_matrix)
        semantic_scores = np.zeros_like(word_scores)
        if self.semantic_model is not None and self.semantic_matrix is not None:
            semantic_query = self.semantic_model.transform(word_query)
            semantic_scores = cosine_similarity(semantic_query, self.semantic_matrix)
        return 0.52 * word_scores + 0.25 * char_scores + 0.23 * semantic_scores

    @staticmethod
    def _softmax_probabilities(raw_scores: np.ndarray, candidate_indices: np.ndarray) -> np.ndarray:
        probabilities = np.zeros_like(raw_scores, dtype=float)
        if not len(candidate_indices):
            return probabilities
        ranked = candidate_indices[np.argsort(raw_scores[candidate_indices])[::-1]]
        pool = ranked[: min(30, len(ranked))]
        values = raw_scores[pool]
        # Temperatura baja para que una evidencia clara produzca una probabilidad útil,
        # manteniendo incertidumbre cuando las primeras alternativas están próximas.
        temperature = 0.085
        logits = (values - float(values.max())) / temperature
        exp_values = np.exp(np.clip(logits, -40, 0))
        pool_probabilities = exp_values / max(float(exp_values.sum()), 1e-12)
        probabilities[pool] = pool_probabilities
        return probabilities

    @staticmethod
    def _confidence(probability: float, margin: float, relevance: float) -> str:
        if probability >= 0.70 and margin >= 0.18 and relevance >= 0.34:
            return "Alta"
        if probability >= 0.45 and margin >= 0.08 and relevance >= 0.22:
            return "Media"
        return "Baja"

    def _rank(
        self,
        filename: str,
        text: str,
        dependency_code: str | None,
    ) -> tuple[np.ndarray, np.ndarray, list[list[str]], dict[str, Any]]:
        filename_norm = normalize_text(filename)
        primary_heading = _primary_heading(filename, text)
        primary_norm = normalize_text(primary_heading)
        header = _title_zone(filename, text)
        header_norm = normalize_text(header)
        body = normalize_text(text)[:100_000]
        chunks = _split_chunks(text)
        if not chunks and body:
            chunks = [body]

        similarity_values = [filename_norm, primary_norm, header_norm, body, *chunks]
        similarities = self._similarity(similarity_values)
        filename_scores = similarities[0]
        primary_scores = similarities[1]
        header_scores = similarities[2]
        body_scores = similarities[3]
        chunk_matrix = similarities[4:] if len(similarities) > 4 else np.zeros((0, len(self.entries)))

        allowed = np.ones(len(self.entries), dtype=bool)
        if dependency_code:
            allowed = np.array(
                [str(entry.get("dependency_code")) == str(dependency_code) for entry in self.entries]
            )
        candidate_indices = np.where(allowed)[0]
        if not len(candidate_indices):
            return np.zeros(len(self.entries)), allowed, [[] for _ in self.entries], {}

        chunk_consensus = np.zeros(len(self.entries), dtype=float)
        chunk_vote_share = np.zeros(len(self.entries), dtype=float)
        if len(chunk_matrix):
            top_per_chunk: list[int] = []
            for row in chunk_matrix:
                local = candidate_indices[np.argmax(row[candidate_indices])]
                top_per_chunk.append(int(local))
            votes = Counter(top_per_chunk)
            for index in candidate_indices:
                values = np.sort(chunk_matrix[:, index])
                strongest = values[-min(3, len(values)) :]
                chunk_consensus[index] = float(strongest.mean()) if len(strongest) else 0.0
                chunk_vote_share[index] = votes.get(int(index), 0) / max(1, len(chunk_matrix))

        raw_scores = (
            0.10 * filename_scores
            + 0.36 * primary_scores
            + 0.20 * header_scores
            + 0.18 * body_scores
            + 0.10 * chunk_consensus
            + 0.06 * chunk_vote_share
        )

        primary_tokens = _tokens(primary_norm)
        header_tokens = _tokens(header_norm)
        filename_tokens = _tokens(filename_norm)
        title_kind = _detect_kind(primary_norm)
        title_intents = _intent_flags(f"{filename_norm} {primary_norm} {header_norm}")
        body_intents = _intent_flags(body)
        query_codes = set(re.findall(r"(?<!\d)\d+(?:\.\d+){1,3}(?!\d)", f"{filename_norm} {header_norm}"))
        evidence: list[list[str]] = [[] for _ in self.entries]

        for index in candidate_indices:
            entry = self.entries[int(index)]
            code = str(entry.get("code", ""))
            dep_code = str(entry.get("dependency_code", ""))
            series = normalize_text(entry.get("series_name", ""))
            subseries = normalize_text(entry.get("subseries_name", ""))
            document_types = entry.get("document_types") or []
            if isinstance(document_types, str):
                document_types = [document_types]

            if code and code in query_codes:
                raw_scores[index] += 0.52
                evidence[index].append("Código TRD localizado en el documento")
            elif dep_code and dep_code in query_codes:
                raw_scores[index] += 0.05

            # La línea principal domina sobre menciones incidentales posteriores.
            if subseries:
                primary_coverage = _coverage(primary_tokens | filename_tokens, subseries)
                if subseries in primary_norm:
                    raw_scores[index] += 0.38
                    evidence[index].append("Subserie identificada en el título principal")
                elif primary_coverage >= 0.78:
                    raw_scores[index] += 0.34 * primary_coverage
                    evidence[index].append("Título principal coincide con la subserie")
                elif primary_coverage >= 0.55:
                    raw_scores[index] += 0.16 * primary_coverage
                elif subseries in header_norm:
                    raw_scores[index] += 0.07

            if series:
                primary_series_coverage = _coverage(primary_tokens | filename_tokens, series)
                if series in primary_norm:
                    raw_scores[index] += 0.18
                    evidence[index].append("Serie identificada en el título principal")
                elif primary_series_coverage >= 0.80:
                    raw_scores[index] += 0.13 * primary_series_coverage
                elif series in header_norm:
                    raw_scores[index] += 0.04

            best_type_coverage = 0.0
            exact_type = ""
            for document_type in document_types:
                value = normalize_text(document_type)
                if value and len(value) >= 4 and value in primary_norm:
                    exact_type = str(document_type)
                    best_type_coverage = 1.0
                    break
                best_type_coverage = max(
                    best_type_coverage,
                    _coverage(primary_tokens | filename_tokens, document_type),
                )
            if exact_type:
                raw_scores[index] += 0.24
                evidence[index].append(f"Tipo documental en encabezado: {exact_type}")
            elif best_type_coverage >= 0.75:
                raw_scores[index] += 0.15 * best_type_coverage
                evidence[index].append("Tipo documental compatible con el título")

            if title_kind:
                if title_kind in self.entry_kinds[int(index)]:
                    raw_scores[index] += 0.14
                    evidence[index].append(f"Tipología dominante: {title_kind}")
                else:
                    raw_scores[index] -= 0.09

            entry_intents = self.entry_intents[int(index)]
            # Regla de desambiguación: PRÉSTAMO y PRUEBA no son equivalentes, aunque
            # el OCR o los n-gramas de caracteres los aproximen. El título manda.
            if "prestamo" in title_intents:
                if "prestamo" in entry_intents:
                    raw_scores[index] += 0.24
                    evidence[index].append("Préstamo identificado en el título")
                elif "prueba" in entry_intents:
                    raw_scores[index] -= 0.32
            elif "prestamo" in body_intents and "prestamo" in entry_intents:
                raw_scores[index] += 0.10

            if "prueba" in title_intents:
                if "prueba" in entry_intents:
                    raw_scores[index] += 0.18
                elif "prestamo" in entry_intents:
                    raw_scores[index] -= 0.20

            if {"prestamo", "historia_clinica"}.issubset(title_intents):
                if {"prestamo", "historia_clinica"}.issubset(entry_intents):
                    raw_scores[index] += 0.48
                    evidence[index].append("Título específico: préstamo de historias clínicas")
                elif "prueba" in entry_intents:
                    raw_scores[index] -= 0.38
            elif {"prestamo", "historia_clinica"}.issubset(body_intents):
                if {"prestamo", "historia_clinica"}.issubset(entry_intents):
                    raw_scores[index] += 0.20

            if "registro_control" in title_intents and "registro_control" in entry_intents:
                raw_scores[index] += 0.07
            if "resultado" in title_intents and "resultado" in entry_intents:
                raw_scores[index] += 0.06

            if len(chunks) >= 2 and chunk_vote_share[index] >= 0.50:
                raw_scores[index] += 0.08 * chunk_vote_share[index]
                evidence[index].append("Coincidencia dominante en varias páginas o bloques")
            elif chunk_vote_share[index] == 0 and len(chunks) >= 4:
                raw_scores[index] -= 0.025

        raw_scores = np.clip(raw_scores, 0.0, 1.8)
        metadata = {
            "model_version": MODEL_VERSION,
            "primary_heading": primary_heading[:500],
            "title_zone": header[:1_000],
            "title_kind": title_kind,
            "title_intents": sorted(title_intents),
            "chunks_analyzed": len(chunks),
        }
        return raw_scores, allowed, evidence, metadata

    def classify(
        self,
        filename: str,
        text: str,
        dependency_code: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        raw_scores, allowed, evidence, metadata = self._rank(filename, text, dependency_code)
        candidate_indices = np.where(allowed)[0]
        if not len(candidate_indices):
            return []

        probabilities = self._softmax_probabilities(raw_scores, candidate_indices)
        ranked = candidate_indices[np.argsort(raw_scores[candidate_indices])[::-1]][: max(1, int(top_k))]
        top_probability = float(probabilities[int(ranked[0])]) if len(ranked) else 0.0
        second_probability = float(probabilities[int(ranked[1])]) if len(ranked) > 1 else 0.0
        probability_margin = max(0.0, top_probability - second_probability)
        top_raw = float(raw_scores[int(ranked[0])]) if len(ranked) else 0.0
        second_raw = float(raw_scores[int(ranked[1])]) if len(ranked) > 1 else 0.0
        raw_margin = max(0.0, top_raw - second_raw)

        results: list[dict[str, Any]] = []
        for position, index in enumerate(ranked):
            entry = dict(self.entries[int(index)])
            probability = float(probabilities[int(index)])
            relevance = float(min(1.0, raw_scores[int(index)] / 1.25))
            margin = probability_margin if position == 0 else 0.0
            confidence = self._confidence(probability, margin, relevance)
            entry.update(
                {
                    "score": round(probability, 6),
                    "score_percent": round(probability * 100, 1),
                    "probability": round(probability, 6),
                    "probability_percent": round(probability * 100, 1),
                    "relevance_score": round(relevance, 6),
                    "relevance_percent": round(relevance * 100, 1),
                    "confidence": confidence,
                    "margin": round(margin, 6),
                    "raw_margin": round(raw_margin, 6) if position == 0 else 0.0,
                    "needs_review": bool(
                        position == 0
                        and (probability < 0.48 or probability_margin < 0.08 or relevance < 0.20)
                    ),
                    "evidence": evidence[int(index)][:5],
                    "model_version": MODEL_VERSION,
                    "analysis": metadata if position == 0 else {"model_version": MODEL_VERSION},
                }
            )
            results.append(entry)
        return results

    def search(
        self,
        query: str,
        dependency_code: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        return self.classify(query, query, dependency_code=dependency_code, top_k=top_k)
