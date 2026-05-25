"""Tests du writer (extraction + dedup) + reader (top-k cosine)."""

from __future__ import annotations

from pathlib import Path

from jarvis_memory.embedder import HashEmbedder
from jarvis_memory.reader import MemoryReader
from jarvis_memory.store import MemoryStore
from jarvis_memory.writer import MemoryWriter

# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def _writer(tmp_path: Path) -> tuple[MemoryStore, MemoryWriter, HashEmbedder]:
    store = MemoryStore(tmp_path / "mem.db")
    embedder = HashEmbedder()
    writer = MemoryWriter(store, embedder)
    return store, writer, embedder


def test_writer_add_fact_creates_with_embedding(tmp_path: Path) -> None:
    store, writer, _ = _writer(tmp_path)
    res = writer.add_fact("L'utilisateur préfère le café noir", kind="biography")
    assert res is not None
    assert res.duplicate is False
    assert res.fact.embedding is not None
    assert len(res.fact.embedding) > 0
    assert store.count() == 1


def test_writer_dedup_returns_existing(tmp_path: Path) -> None:
    store, writer, _ = _writer(tmp_path)
    first = writer.add_fact("Noah aime le café", kind="biography")
    second = writer.add_fact("Noah aime le café", kind="biography")
    assert first is not None and second is not None
    assert second.duplicate is True
    assert second.fact_id == first.fact_id
    assert store.count() == 1


def test_writer_refuses_credentials(tmp_path: Path) -> None:
    store, writer, _ = _writer(tmp_path)
    res = writer.add_fact("password123", kind="credential")
    assert res is None
    assert store.count() == 0


def test_writer_refuses_empty(tmp_path: Path) -> None:
    _, writer, _ = _writer(tmp_path)
    assert writer.add_fact("", kind="biography") is None
    assert writer.add_fact("   ", kind="biography") is None


def test_extract_from_text_finds_biography(tmp_path: Path) -> None:
    _store, writer, _ = _writer(tmp_path)
    results = writer.extract_from_text("Salut Jarvis, je préfère le café noir le matin.")
    assert len(results) >= 1
    facts = [r.fact for r in results]
    # Le pattern capture le complément du verbe ; le verbe lui-même est consommé.
    # On normalise en "L'utilisateur ..." donc le café noir apparaît bien.
    assert any("café noir" in f.text for f in facts)
    assert all(f.kind == "biography" for f in facts)
    assert any(f.text.startswith("L'utilisateur") for f in facts)


def test_extract_from_text_finds_user_directive(tmp_path: Path) -> None:
    _, writer, _ = _writer(tmp_path)
    results = writer.extract_from_text("Rappelle-toi que je travaille sur Jarvis.")
    assert any("travaille sur Jarvis" in r.fact.text for r in results)
    assert any(r.fact.kind == "user_directive" for r in results)


def test_extract_from_text_skips_credentials(tmp_path: Path) -> None:
    _store, writer, _ = _writer(tmp_path)
    # Le pattern credential match mais skip_kinds le refuse
    results = writer.extract_from_text("mon mot de passe est secret123")
    assert all(r.fact.kind != "credential" for r in results)


def test_extract_from_text_no_match(tmp_path: Path) -> None:
    _store, writer, _ = _writer(tmp_path)
    results = writer.extract_from_text("blabla quelconque sans pattern")
    assert results == []


# ---------------------------------------------------------------------------
# Reader (cosine top-k)
# ---------------------------------------------------------------------------


def test_reader_returns_empty_on_empty_query(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    reader = MemoryReader(store, HashEmbedder())
    assert reader.search("") == []
    assert reader.search("   ") == []


def test_reader_returns_self_match(tmp_path: Path) -> None:
    """Avec HashEmbedder, le top-1 d'une query exacte doit être ce texte exact."""
    store, writer, embedder = _writer(tmp_path)
    writer.add_fact("Noah aime le café noir")
    writer.add_fact("Le ciel est bleu aujourd'hui")
    writer.add_fact("Les chats préfèrent dormir")
    reader = MemoryReader(store, embedder)
    results = reader.search("Noah aime le café noir", top_k=1)
    assert len(results) == 1
    assert results[0].fact.text == "Noah aime le café noir"
    assert results[0].score > 0.999  # quasi 1.0 self-match


def test_reader_top_k_limit(tmp_path: Path) -> None:
    store, writer, embedder = _writer(tmp_path)
    for i in range(10):
        writer.add_fact(f"fact numéro {i}")
    reader = MemoryReader(store, embedder)
    results = reader.search("fact", top_k=3)
    assert len(results) == 3


def test_reader_filters_by_kind(tmp_path: Path) -> None:
    store, writer, embedder = _writer(tmp_path)
    writer.add_fact("Noah aime le code", kind="biography")
    writer.add_fact("Toujours commit avant push", kind="user_directive")
    reader = MemoryReader(store, embedder)
    results = reader.search("Noah", top_k=10, kind="biography")
    assert all(r.fact.kind == "biography" for r in results)


def test_reader_min_score_filter(tmp_path: Path) -> None:
    store, writer, embedder = _writer(tmp_path)
    writer.add_fact("totalement unrelated")
    reader = MemoryReader(store, embedder)
    # Score quasi nul vs query random + min_score élevé → résultats vides
    results = reader.search("autre chose qui n'a rien à voir", top_k=5, min_score=0.5)
    assert results == []


def test_reader_results_sorted_descending(tmp_path: Path) -> None:
    store, writer, embedder = _writer(tmp_path)
    for i in range(5):
        writer.add_fact(f"texte différent {i}")
    reader = MemoryReader(store, embedder)
    results = reader.search("texte", top_k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
