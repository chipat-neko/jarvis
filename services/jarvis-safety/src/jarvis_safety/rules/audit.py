"""Audit log SQLite append-only.

Toutes les actions de Jarvis sont loggées dans une SQLite append-only
(`.local/audit_log.db` par défaut). Sert pour :
- Debug ("pourquoi Jarvis a fait X ?")
- Compliance ("quelles données ont été lues ?")
- Replay ("rejoue le contexte d'une décision")

Schéma simple : une table `events` avec timestamp + actor + action + payload
JSON + status. Pas d'index pour pas pénaliser les writes en append-only.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Un événement consigné dans le log."""

    actor: str  # "user", "llm", "tool", "system"
    action: str  # ex "chat.complete", "tool.read_file", "rule.blacklist_match"
    payload: dict = field(default_factory=dict)
    status: str = "ok"  # "ok", "refused", "error"
    timestamp: str = ""  # ISO 8601, rempli par AuditLogger.log()


class AuditLogger:
    """Logger SQLite append-only thread-safe.

    Construit la base si elle n'existe pas. Une seule table `events`.
    Toutes les écritures dans le mutex `_lock` pour éviter les race conditions
    quand plusieurs threads (gRPC handlers) loggent en parallèle.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT NOT NULL,
        actor       TEXT NOT NULL,
        action      TEXT NOT NULL,
        status      TEXT NOT NULL,
        payload     TEXT NOT NULL
    )
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False car on protège par mutex côté Python.
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(self.SCHEMA)
            conn.commit()

    def log(self, event: AuditEvent) -> int:
        """Insère un event, retourne l'id généré."""
        ts = event.timestamp or datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO events (timestamp, actor, action, status, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    ts,
                    event.actor,
                    event.action,
                    event.status,
                    json.dumps(event.payload, ensure_ascii=False),
                ),
            )
            conn.commit()
            return cur.lastrowid

    def recent(self, limit: int = 100) -> list[dict]:
        """Lit les N derniers events, ordre décroissant."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT id, timestamp, actor, action, status, payload "
                "FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "timestamp": row[1],
                "actor": row[2],
                "action": row[3],
                "status": row[4],
                "payload": json.loads(row[5]) if row[5] else {},
            }
            for row in rows
        ]

    def count(self) -> int:
        """Nombre total d'events."""
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM events")
            return int(cur.fetchone()[0])

    def event_dict(self, event: AuditEvent) -> dict:
        """Helper pour debug / display."""
        return asdict(event)
