from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


SPANISH_STOP_WORDS = {
    "a", "al", "algo", "ante", "bajo", "cada", "como", "con", "contra", "cual", "cuando",
    "de", "del", "desde", "donde", "dos", "el", "ella", "ellos", "en", "entre", "era", "es",
    "esa", "ese", "esta", "este", "fue", "ha", "hasta", "la", "las", "lo", "los", "mas", "muy",
    "no", "o", "para", "pero", "por", "que", "se", "ser", "si", "sin", "sobre", "son", "su",
    "sus", "tambien", "todo", "un", "una", "uno", "y", "ya",
}


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").lower()
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def _entry_training_text(entry: dict[str, Any]) -> str:
    dependency = entry.get("dependency_name", "")
    series = entry.get("series_name", "")
    subseries = entry.get("subseries_name", "")
    document_types = " ".join(entry.get("document_types") or [])
    procedure = str(entry.get("procedure", ""))[:4_000]
    # La repetición pondera los campos archivísticos más discriminantes.
    return normalize_text(
        " ".join(
            [
                entry.get("code", ""),
                entry.get("dependency_code", ""),
                dependency,
                dependency,
                series,
                series,
                series,
                subseries,
                subseries,
                subseries,
                document_types,
                document_types,
                procedure,
            ]
        )
    )


class DocumentClassifier:
    """Clasificador no supervisado, local y explicable basado en recuperación TF-IDF."""

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
            text = normalize_text(example.get("text", ""))[:8_000]
            if code and text:
                examples_by_code[code].append(text)

        self.training_texts = []
        for entry in self.entries:
            base = _entry_training_text(entry)
            examples = " ".join(examples_by_code.get(str(entry.get("code")), [])[-8:])
            self.training_texts.append(f"{base} {examples}".strip())

        self.word_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            max_df=1.0,
            max_features=60_000,
            sublinear_tf=True,
            stop_words=list(SPANISH_STOP_WORDS),
            token_pattern=r"(?u)\b[\w.-]{2,}\b",
        )
        self.char_vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=1,
            max_features=80_000,
            sublinear_tf=True,
        )
        self.word_matrix = self.word_vectorizer.fit_transform(self.training_texts)
        self.char_matrix = self.char_vectorizer.fit_transform(self.training_texts)

    def _query(self, filename: str, text: str) -> str:
        filename_text = normalize_text(filename)
        content = normalize_text(text)[:40_000]
        return f"{filename_text} {filename_text} {filename_text} {content}".strip()

    def _score(self, query: str) -> np.ndarray:
        word_query = self.word_vectorizer.transform([query])
        char_query = self.char_vectorizer.transform([query])
        word_scores = cosine_similarity(word_query, self.word_matrix).ravel()
        char_scores = cosine_similarity(char_query, self.char_matrix).ravel()
        scores = 0.68 * word_scores + 0.32 * char_scores

        query_tokens = set(re.findall(r"\b\d+(?:\.\d+){1,3}\b", query))
        for index, entry in enumerate(self.entries):
            code = str(entry.get("code", ""))
            dep_code = str(entry.get("dependency_code", ""))
            if code and code in query_tokens:
                scores[index] += 0.40
            elif dep_code and dep_code in query_tokens:
                scores[index] += 0.06
        return np.clip(scores, 0.0, 1.0)

    @staticmethod
    def _confidence(score: float) -> str:
        if score >= 0.45:
            return "Alta"
        if score >= 0.25:
            return "Media"
        return "Baja"

    def classify(
        self,
        filename: str,
        text: str,
        dependency_code: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        query = self._query(filename, text)
        scores = self._score(query)
        allowed = np.ones(len(self.entries), dtype=bool)
        if dependency_code:
            allowed = np.array([str(e.get("dependency_code")) == str(dependency_code) for e in self.entries])
        candidate_indices = np.where(allowed)[0]
        if not len(candidate_indices):
            return []
        ranked = candidate_indices[np.argsort(scores[candidate_indices])[::-1]][: max(1, top_k)]
        results = []
        for index in ranked:
            entry = dict(self.entries[int(index)])
            score = float(scores[int(index)])
            entry["score"] = round(score, 4)
            entry["score_percent"] = round(score * 100, 1)
            entry["confidence"] = self._confidence(score)
            results.append(entry)
        return results

    def search(
        self,
        query: str,
        dependency_code: str | None = None,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        return self.classify(query, query, dependency_code=dependency_code, top_k=top_k)
