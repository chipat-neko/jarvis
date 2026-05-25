"""Tests du MemoryStore SQLite (CRUD + embeddings)."""

from __future__ import annotations

import time
from pathlib import Path

from jarvis_memory.store import Fact, MemoryStore


def _make_fact(text: str = "hello", *, kind: str = "biography") -> Fact:
    return Fact(
        id=None,
        ts=time.time(),
        kind=kind,
        text=text,
        source="test",
        metadata={"k": "v"},
        embedding=[0.1, 0.2, 0.3, 0.4],
    )


def test_store_init_creates_db(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    MemoryStore(db)
    assert db.exists()


def test_add_and_get_fact(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    f = _make_fact("Noah aime le café noir")
    fid = store.add(f)
    assert fid > 0
    loaded = store.get(fid)
    assert loaded is not None
    assert loaded.text == "Noah aime le café noir"
    assert loaded.kind == "biography"
    assert loaded.metadata == {"k": "v"}


def test_embedding_roundtrip(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    f = Fact(
        id=None,
        ts=time.time(),
        kind="x",
        text="hi",
        embedding=[0.1, 0.2, -0.3, 0.4],
    )
    fid = store.add(f)
    loaded = store.get(fid)
    assert loaded is not None
    assert loaded.embedding is not None
    assert len(loaded.embedding) == 4
    # struct '<f' a une précision limitée (float32), donc on tolère un epsilon
    for original, restored in zip([0.1, 0.2, -0.3, 0.4], loaded.embedding, strict=True):
        assert abs(original - restored) < 1e-6


def test_count(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    assert store.count() == 0
    store.add(_make_fact("a"))
    store.add(_make_fact("b"))
    assert store.count() == 2


def test_all_with_embeddings_filters(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    # Sans embedding → exclu
    store.add(Fact(id=None, ts=time.time(), kind="x", text="no emb"))
    store.add(_make_fact("with emb"))
    facts = store.all_with_embeddings()
    assert len(facts) == 1
    assert facts[0].text == "with emb"


def test_all_with_embeddings_by_kind(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    store.add(_make_fact("a", kind="biography"))
    store.add(_make_fact("b", kind="user_directive"))
    bios = store.all_with_embeddings(kind="biography")
    assert len(bios) == 1
    assert bios[0].kind == "biography"


def test_delete(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    fid = store.add(_make_fact("to be deleted"))
    assert store.delete(fid) is True
    assert store.get(fid) is None
    assert store.delete(fid) is False  # second delete = no-op


def test_find_by_text_returns_duplicates(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    store.add(_make_fact("Noah aime le café"))
    store.add(_make_fact("Noah aime le café"))
    matches = store.find_by_text("Noah aime le café")
    assert len(matches) == 2


def test_find_by_text_no_match(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    store.add(_make_fact("Noah aime le café"))
    assert store.find_by_text("autre chose") == []
