from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer


BANTER_SOURCE_URL = "https://observatorioagn.archivogeneral.gov.co/banter/"


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9áéíóúüñ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_banter_reference(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {}, [dict(item) for item in payload]
    return dict(payload.get("metadata") or {}), [dict(item) for item in payload.get("terms") or []]


def _training_text(term: dict[str, Any]) -> str:
    series = str(term.get("series_name") or term.get("series") or "")
    subseries = str(term.get("subseries_name") or term.get("subseries") or "")
    definition = str(term.get("definition") or "")
    functional_group = str(term.get("functional_group") or "")
    aliases = " ".join(str(value) for value in term.get("aliases") or [])
    document_types = " ".join(str(value) for value in term.get("document_types") or [])
    return normalize_text(
        " ".join(
            [
                series,
                series,
                series,
                subseries,
                subseries,
                subseries,
                functional_group,
                aliases,
                aliases,
                document_types,
                definition,
            ]
        )
    )


class BanterSearchEngine:
    """Motor local gratuito para recuperar términos BANTER mediante TF-IDF y LSA.

    No usa API, no envía documentos a servicios externos y funciona sin conexión.
    La salida es una recomendación orientativa y no crea códigos TRD oficiales.
    """

    def __init__(self, terms: Iterable[dict[str, Any]]) -> None:
        self.terms = [dict(term) for term in terms]
        if not self.terms:
            raise ValueError("El banco BANTER local no contiene términos.")
        self.training_texts = [_training_text(term) for term in self.terms]

        self.word_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            max_features=45_000,
            sublinear_tf=True,
            token_pattern=r"(?u)\b[\w.-]{2,}\b",
        )
        self.char_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            max_features=55_000,
            sublinear_tf=True,
        )
        self.word_matrix = self.word_vectorizer.fit_transform(self.training_texts)
        self.char_matrix = self.char_vectorizer.fit_transform(self.training_texts)

        max_components = min(96, max(1, self.word_matrix.shape[0] - 1), max(1, self.word_matrix.shape[1] - 1))
        self.semantic_model = None
        self.semantic_matrix = None
        if max_components >= 2:
            self.semantic_model = make_pipeline(
                TruncatedSVD(n_components=max_components, random_state=42),
                Normalizer(copy=False),
            )
            self.semantic_matrix = self.semantic_model.fit_transform(self.word_matrix)

    @staticmethod
    def _confidence(score: float) -> str:
        if score >= 0.56:
            return "Alta"
        if score >= 0.32:
            return "Media"
        return "Baja"

    def search(self, query: str, top_k: int = 12, series_name: str | None = None) -> list[dict[str, Any]]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            return []
        word_query = self.word_vectorizer.transform([normalized_query])
        char_query = self.char_vectorizer.transform([normalized_query])
        word_scores = cosine_similarity(word_query, self.word_matrix).ravel()
        char_scores = cosine_similarity(char_query, self.char_matrix).ravel()
        semantic_scores = np.zeros(len(self.terms), dtype=float)
        if self.semantic_model is not None and self.semantic_matrix is not None:
            semantic_query = self.semantic_model.transform(word_query)
            semantic_scores = cosine_similarity(semantic_query, self.semantic_matrix).ravel()
        scores = 0.48 * word_scores + 0.27 * char_scores + 0.25 * semantic_scores

        query_words = set(normalized_query.split())
        allowed = np.ones(len(self.terms), dtype=bool)
        if series_name:
            expected = normalize_text(series_name)
            allowed = np.array(
                [normalize_text(term.get("series_name") or term.get("series")) == expected for term in self.terms]
            )

        for index, term in enumerate(self.terms):
            series = normalize_text(term.get("series_name") or term.get("series"))
            subseries = normalize_text(term.get("subseries_name") or term.get("subseries"))
            aliases = [normalize_text(value) for value in term.get("aliases") or []]
            for value, bonus in ((subseries, 0.22), (series, 0.14)):
                if value and value in normalized_query:
                    scores[index] += bonus
            alias_tokens = set(" ".join(aliases).split())
            if alias_tokens and len(alias_tokens & query_words) / max(1, len(alias_tokens)) >= 0.45:
                scores[index] += 0.08

        candidate_indices = np.where(allowed)[0]
        if not len(candidate_indices):
            return []
        ranked = candidate_indices[np.argsort(scores[candidate_indices])[::-1]][: max(1, int(top_k))]
        results: list[dict[str, Any]] = []
        top_score = float(scores[int(ranked[0])]) if len(ranked) else 0.0
        second_score = float(scores[int(ranked[1])]) if len(ranked) > 1 else 0.0
        margin = max(0.0, top_score - second_score)
        for position, index in enumerate(ranked):
            term = dict(self.terms[int(index)])
            term["series_name"] = term.get("series_name") or term.get("series") or ""
            term["subseries_name"] = term.get("subseries_name") or term.get("subseries") or ""
            score = float(np.clip(scores[int(index)], 0.0, 1.0))
            term.update(
                {
                    "score": round(score, 4),
                    "score_percent": round(score * 100, 1),
                    "confidence": self._confidence(score),
                    "margin": round(margin, 4) if position == 0 else 0.0,
                    "source": "BANTER AGN — referencia orientativa",
                    "source_url": BANTER_SOURCE_URL,
                    "is_banter": True,
                    "needs_review": bool(position == 0 and (score < 0.32 or margin < 0.03)),
                }
            )
            results.append(term)
        return results


def to_custom_classification(
    term: dict[str, Any],
    dependency_code: str = "",
    dependency_name: str = "",
) -> dict[str, Any]:
    return {
        "is_other": True,
        "is_banter": True,
        "source": "BANTER AGN — referencia orientativa",
        "source_url": BANTER_SOURCE_URL,
        "code": "",
        "dependency_code": dependency_code,
        "dependency_name": dependency_name,
        "series_code": "",
        "series_name": str(term.get("series_name") or term.get("series") or "SERIE POR VALIDAR"),
        "subseries_code": "",
        "subseries_name": str(term.get("subseries_name") or term.get("subseries") or ""),
        "document_types": [str(value) for value in term.get("document_types") or []],
        "retention_management": "",
        "retention_central": "",
        "final_disposition": [],
        "functional_group": str(term.get("functional_group") or ""),
        "definition": str(term.get("definition") or ""),
        "procedure": (
            "Denominación sugerida con apoyo del BANTER del Archivo General de la Nación. "
            "No asigna código ni modifica automáticamente la TRD/CCD; requiere validación archivística institucional."
        ),
    }
