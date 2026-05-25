"""Tests de l'audit log SQLite."""

from __future__ import annotations

from pathlib import Path

from jarvis_safety.rules.audit import AuditEvent, AuditLogger


def test_log_inserts_event(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    eid = logger.log(AuditEvent(actor="user", action="chat.complete", payload={"tokens": 42}))
    assert eid > 0
    assert logger.count() == 1


def test_log_persists_payload_json(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    logger.log(
        AuditEvent(actor="tool", action="fs.read", payload={"path": "/tmp/x", "size": 12}),
    )
    events = logger.recent(10)
    assert len(events) == 1
    assert events[0]["payload"]["path"] == "/tmp/x"
    assert events[0]["payload"]["size"] == 12


def test_recent_returns_descending(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    for i in range(5):
        logger.log(AuditEvent(actor="user", action="evt", payload={"n": i}))
    events = logger.recent(3)
    assert len(events) == 3
    # Le plus récent en premier
    assert events[0]["payload"]["n"] == 4
    assert events[2]["payload"]["n"] == 2


def test_status_field(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    logger.log(AuditEvent(actor="rule", action="blacklist.match", status="refused", payload={}))
    events = logger.recent(1)
    assert events[0]["status"] == "refused"


def test_parent_dir_auto_created(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "audit.db"
    logger = AuditLogger(nested)
    logger.log(AuditEvent(actor="x", action="y", payload={}))
    assert nested.exists()


def test_count_returns_zero_initially(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    assert logger.count() == 0


def test_unicode_payload(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.db")
    logger.log(AuditEvent(actor="user", action="chat", payload={"text": "héllo wörld 🚀"}))
    events = logger.recent(1)
    assert events[0]["payload"]["text"] == "héllo wörld 🚀"


def test_persistence_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    logger1 = AuditLogger(db_path)
    logger1.log(AuditEvent(actor="user", action="x", payload={"n": 1}))

    # Nouvelle instance, même fichier
    logger2 = AuditLogger(db_path)
    assert logger2.count() == 1
    logger2.log(AuditEvent(actor="user", action="x", payload={"n": 2}))
    assert logger2.count() == 2
