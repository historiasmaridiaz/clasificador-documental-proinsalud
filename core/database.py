from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .text_extract import DocumentPayload, ExtractedDocument


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_filename(value: str, fallback: str = "archivo") -> str:
    name = Path(value.replace("\\", "/")).name
    name = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" ._")
    return name[:180] or fallback


class Database:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir = self.data_dir / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "clasificador.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalog_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    entries_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    extension TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    extracted_text TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    uploaded_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL UNIQUE,
                    catalog_version_id INTEGER,
                    suggested_code TEXT NOT NULL DEFAULT '',
                    suggested_score REAL NOT NULL DEFAULT 0,
                    confidence TEXT NOT NULL DEFAULT 'Baja',
                    candidates_json TEXT NOT NULL DEFAULT '[]',
                    final_code TEXT NOT NULL DEFAULT '',
                    document_year TEXT NOT NULL DEFAULT '',
                    year_source TEXT NOT NULL DEFAULT '',
                    year_confidence REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'Pendiente',
                    reviewer_notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                    FOREIGN KEY(catalog_version_id) REFERENCES catalog_versions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_classification_status ON classifications(status);
                CREATE INDEX IF NOT EXISTS idx_classification_code ON classifications(final_code);
                """
            )
            self._ensure_column(connection, "classifications", "document_year", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "classifications", "year_source", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "classifications", "year_confidence", "REAL NOT NULL DEFAULT 0")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def seed_catalog(self, name: str, entries: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> int:
        with self._connect() as connection:
            existing = connection.execute("SELECT id FROM catalog_versions LIMIT 1").fetchone()
            if existing:
                return int(existing["id"])
        return self.save_catalog(name, entries, metadata or {})

    def save_catalog(self, name: str, entries: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> int:
        if not entries:
            raise ValueError("No se puede activar un catálogo vacío.")
        with self._connect() as connection:
            connection.execute("UPDATE catalog_versions SET is_active = 0")
            cursor = connection.execute(
                "INSERT INTO catalog_versions(name, entries_json, metadata_json, created_at, is_active) VALUES (?, ?, ?, ?, 1)",
                (
                    name.strip() or "Catálogo sin nombre",
                    json.dumps(entries, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_catalogs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, metadata_json, created_at, is_active FROM catalog_versions ORDER BY id DESC"
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "name": row["name"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    def activate_catalog(self, catalog_id: int) -> None:
        with self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM catalog_versions WHERE id = ?", (catalog_id,)).fetchone()
            if not exists:
                raise ValueError("La versión de catálogo no existe.")
            connection.execute("UPDATE catalog_versions SET is_active = 0")
            connection.execute("UPDATE catalog_versions SET is_active = 1 WHERE id = ?", (catalog_id,))

    def active_catalog(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, entries_json, metadata_json, created_at FROM catalog_versions WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            raise RuntimeError("No existe un catálogo activo.")
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "entries": json.loads(row["entries_json"]),
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def save_document(self, payload: DocumentPayload, extracted: ExtractedDocument) -> int:
        stored_name = f"{payload.sha256[:16]}_{safe_filename(payload.name)}"
        stored_path = self.upload_dir / stored_name
        if not stored_path.exists():
            stored_path.write_bytes(payload.data)
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM documents WHERE sha256 = ?", (payload.sha256,)).fetchone()
            if row:
                connection.execute(
                    """UPDATE documents SET filename=?, extension=?, stored_path=?, extracted_text=?, metadata_json=?,
                       warnings_json=?, uploaded_at=? WHERE id=?""",
                    (
                        payload.name,
                        extracted.extension,
                        str(stored_path),
                        extracted.text,
                        json.dumps(extracted.metadata, ensure_ascii=False),
                        json.dumps(extracted.warnings, ensure_ascii=False),
                        utc_now(),
                        int(row["id"]),
                    ),
                )
                return int(row["id"])
            cursor = connection.execute(
                """INSERT INTO documents(filename, sha256, extension, stored_path, extracted_text, metadata_json,
                   warnings_json, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload.name,
                    payload.sha256,
                    extracted.extension,
                    str(stored_path),
                    extracted.text,
                    json.dumps(extracted.metadata, ensure_ascii=False),
                    json.dumps(extracted.warnings, ensure_ascii=False),
                    utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def save_classification(
        self,
        document_id: int,
        catalog_version_id: int,
        candidates: list[dict[str, Any]],
        document_year: str = "",
        year_source: str = "",
        year_confidence: float = 0.0,
    ) -> int:
        top = candidates[0] if candidates else {}
        code = str(top.get("code", ""))
        score = float(top.get("score", 0.0))
        confidence = str(top.get("confidence", "Baja"))
        now = utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, status, final_code FROM classifications WHERE document_id = ?", (document_id,)
            ).fetchone()
            if existing:
                preserve_review = existing["status"] in {"Aprobada", "Corregida", "Descartada"}
                final_code = existing["final_code"] if preserve_review else code
                status = existing["status"] if preserve_review else "Pendiente"
                connection.execute(
                    """UPDATE classifications SET catalog_version_id=?, suggested_code=?, suggested_score=?, confidence=?,
                       candidates_json=?, final_code=?, document_year=?, year_source=?, year_confidence=?, status=?,
                       updated_at=? WHERE id=?""",
                    (
                        catalog_version_id,
                        code,
                        score,
                        confidence,
                        json.dumps(candidates, ensure_ascii=False),
                        final_code,
                        str(document_year),
                        year_source,
                        float(year_confidence),
                        status,
                        now,
                        int(existing["id"]),
                    ),
                )
                return int(existing["id"])
            cursor = connection.execute(
                """INSERT INTO classifications(document_id, catalog_version_id, suggested_code, suggested_score,
                   confidence, candidates_json, final_code, document_year, year_source, year_confidence, status,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', ?, ?)""",
                (
                    document_id,
                    catalog_version_id,
                    code,
                    score,
                    confidence,
                    json.dumps(candidates, ensure_ascii=False),
                    code,
                    str(document_year),
                    year_source,
                    float(year_confidence),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def list_classifications(self, limit: int = 10_000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.document_id, d.filename, d.sha256, d.extension, d.stored_path, d.extracted_text,
                       d.metadata_json, d.warnings_json, c.catalog_version_id, c.suggested_code,
                       c.suggested_score, c.confidence, c.candidates_json, c.final_code, c.document_year,
                       c.year_source, c.year_confidence, c.status,
                       c.reviewer_notes, c.created_at, c.updated_at
                FROM classifications c JOIN documents d ON d.id = c.document_id
                ORDER BY c.updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            item["warnings"] = json.loads(item.pop("warnings_json"))
            item["candidates"] = json.loads(item.pop("candidates_json"))
            result.append(item)
        return result

    def update_review(
        self,
        classification_id: int,
        final_code: str,
        status: str,
        notes: str = "",
        document_year: str | int | None = None,
    ) -> None:
        allowed = {"Pendiente", "Aprobada", "Corregida", "Descartada"}
        if status not in allowed:
            raise ValueError("Estado de revisión no válido.")
        with self._connect() as connection:
            if document_year is None:
                connection.execute(
                    "UPDATE classifications SET final_code=?, status=?, reviewer_notes=?, updated_at=? WHERE id=?",
                    (final_code.strip(), status, notes.strip(), utc_now(), classification_id),
                )
            else:
                year = str(document_year).strip()
                if not re.fullmatch(r"(?:19|20)\d{2}", year):
                    raise ValueError("El año documental debe tener cuatro dígitos.")
                connection.execute(
                    """UPDATE classifications SET final_code=?, document_year=?, status=?, reviewer_notes=?,
                       updated_at=? WHERE id=?""",
                    (final_code.strip(), year, status, notes.strip(), utc_now(), classification_id),
                )

    def learned_examples(self, limit: int = 2_000) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.final_code AS code, d.filename, d.extracted_text
                   FROM classifications c JOIN documents d ON d.id=c.document_id
                   WHERE c.status IN ('Aprobada', 'Corregida') AND c.final_code <> ''
                   ORDER BY c.updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{"code": row["code"], "text": f"{row['filename']} {row['extracted_text']}"} for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
            pending = connection.execute("SELECT COUNT(*) FROM classifications WHERE status='Pendiente'").fetchone()[0]
            reviewed = connection.execute(
                "SELECT COUNT(*) FROM classifications WHERE status IN ('Aprobada','Corregida')"
            ).fetchone()[0]
        return {"total": int(total), "pending": int(pending), "reviewed": int(reviewed)}
