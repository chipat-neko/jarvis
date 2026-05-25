"""MemoryStore SQLite : persistance des "facts" + vecteurs embeddings.

Schéma minimal :
- `facts` : id, ts, kind, text, source, embedding (BLOB de floats f4),
  metadata (JSON), version.

On stocke les embeddings comme bytes packés (struct '<f' x dim) pour compacité.
Pas de sqlite-vec ni de FAISS : pour < 10k facts perso, brute-force cosine en
Python est < 50ms et garde zéro dépendance lourde.

Thread-safe via Lock + check_same_thread=False (même pattern que AuditLogger).
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock


@dataclass(frozen=True, slots=True)
class Fact:
    """Un fait stocké en mémoire long-terme."""

    id: int | None
    ts: float
    kind: str  # "preference" | "biography" | "decision" | "doc_chunk" | …
    text: str
    source: str = "session"  # "session" | "docs" | "user" | …
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None

    def to_row(self) -> tuple:
        emb_bytes = _pack_embedding(self.embedding) if self.embedding else None
        return (
            self.ts,
            self.kind,
            self.text,
            self.source,
            json.dumps(self.metadata, ensure_ascii=False),
            emb_bytes,
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,
    metadata    TEXT NOT NULL,
    embedding   BLOB
);
CREATE INDEX IF NOT EXISTS facts_kind_idx ON facts(kind);
CREATE INDEX IF NOT EXISTS facts_source_idx ON facts(source);
"""


class MemoryStore:
    """Wrapper SQLite append-only pour les facts.

    Args:
        db_path: chemin du fichier SQLite.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def add(self, fact: Fact) -> int:
        """Insère un fact, retourne l'id généré."""
        ts = fact.ts or time.time()
        emb_bytes = _pack_embedding(fact.embedding) if fact.embedding else None
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO facts (ts, kind, text, source, metadata, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    fact.kind,
                    fact.text,
                    fact.source,
                    json.dumps(fact.metadata, ensure_ascii=False),
                    emb_bytes,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get(self, fact_id: int) -> Fact | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id, ts, kind, text, source, metadata, embedding FROM facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
        return _row_to_fact(row) if row else None

    def all_with_embeddings(self, *, kind: str | None = None) -> list[Fact]:
        """Liste tous les facts qui ont un embedding (pour la similarity search)."""
        sql = (
            "SELECT id, ts, kind, text, source, metadata, embedding FROM facts "
            "WHERE embedding IS NOT NULL"
        )
        params: tuple = ()
        if kind is not None:
            sql += " AND kind = ?"
            params = (kind,)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_fact(r) for r in rows]

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])

    def delete(self, fact_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cur.rowcount > 0

    def find_by_text(self, text: str, *, limit: int = 10) -> list[Fact]:
        """Recherche par texte exact (utilisé pour dédup avant insert)."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, ts, kind, text, source, metadata, embedding "
                "FROM facts WHERE text = ? LIMIT ?",
                (text, limit),
            ).fetchall()
        return [_row_to_fact(r) for r in rows]


def _pack_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_embedding(data: bytes) -> list[float]:
    if not data:
        return []
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))


def _row_to_fact(row: tuple) -> Fact:
    return Fact(
        id=row[0],
        ts=row[1],
        kind=row[2],
        text=row[3],
        source=row[4],
        metadata=json.loads(row[5]) if row[5] else {},
        embedding=_unpack_embedding(row[6]) if row[6] else None,
    )
