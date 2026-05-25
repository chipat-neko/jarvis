"""Tests du RAG indexer : chunking, scan, réindexation propre."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_memory.embedder import HashEmbedder
from jarvis_memory.rag import DocIndexer, _chunk_text, _strip_html
from jarvis_memory.reader import MemoryReader
from jarvis_memory.store import MemoryStore


def _indexer(tmp_path: Path, **kwargs) -> tuple[MemoryStore, DocIndexer]:
    store = MemoryStore(tmp_path / "rag.db")
    indexer = DocIndexer(store, HashEmbedder(), **kwargs)
    return store, indexer


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_short_returns_one() -> None:
    chunks = list(_chunk_text("court", 100, 10))
    assert chunks == ["court"]


def test_chunk_text_size_overlap() -> None:
    text = "a" * 250
    chunks = list(_chunk_text(text, 100, 20))
    # step = 80 → chunks à pos 0, 80, 160, 240 = 4 chunks
    assert len(chunks) == 4
    assert chunks[0] == "a" * 100
    # Overlap : chunks suivants commencent avec un suffixe du précédent
    assert chunks[1].startswith(chunks[0][-20:])
    # Dernier chunk peut être court (residu)
    assert len(chunks[-1]) <= 100


def test_chunk_text_empty() -> None:
    assert list(_chunk_text("", 100, 10)) == []


def test_chunk_text_size_zero() -> None:
    assert list(_chunk_text("hello", 0, 0)) == []


def test_chunk_overlap_invalid_raises() -> None:
    store = MemoryStore("/tmp/notused.db")
    with pytest.raises(ValueError, match="overlap"):
        DocIndexer(store, HashEmbedder(), chunk_size=100, chunk_overlap=100)


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags() -> None:
    text = "<p>Bonjour <strong>Noah</strong></p>"
    assert _strip_html(text) == "Bonjour Noah"


def test_strip_html_removes_script() -> None:
    text = "<p>visible</p><script>alert(1)</script><p>aussi visible</p>"
    out = _strip_html(text)
    assert "alert" not in out
    assert "visible" in out


def test_strip_html_decodes_entities() -> None:
    assert _strip_html("<p>caf&eacute; &amp; th&eacute;</p>") == "café & thé"


def test_strip_html_collapses_whitespace() -> None:
    assert _strip_html("<p>a</p>\n\n   <p>b</p>") == "a b"


# ---------------------------------------------------------------------------
# DocIndexer.index_file
# ---------------------------------------------------------------------------


def test_index_md_file_creates_chunks(tmp_path: Path) -> None:
    f = tmp_path / "note.md"
    f.write_text("# Titre\n\n" + "Bonjour Noah, c'est un test. " * 30, encoding="utf-8")
    store, indexer = _indexer(tmp_path, chunk_size=100, chunk_overlap=20)
    n = indexer.index_file(f)
    assert n > 1  # multi-chunks
    # Tous les chunks ont kind="doc_chunk" et le bon source
    facts = store.all_with_embeddings(kind="doc_chunk")
    assert len(facts) == n
    assert all(f.source == str(tmp_path / "note.md") for f in facts)
    assert all(f.metadata.get("total_chunks") == n for f in facts)


def test_index_html_strips_tags(tmp_path: Path) -> None:
    f = tmp_path / "doc.html"
    f.write_text(
        "<html><body><p>Bonjour Noah, comment vas-tu ?</p></body></html>", encoding="utf-8"
    )
    store, indexer = _indexer(tmp_path)
    n = indexer.index_file(f)
    assert n == 1
    facts = store.all_with_embeddings()
    assert "Bonjour Noah" in facts[0].text
    assert "<body>" not in facts[0].text


def test_index_empty_file_returns_zero(tmp_path: Path) -> None:
    f = tmp_path / "empty.md"
    f.write_text("", encoding="utf-8")
    store, indexer = _indexer(tmp_path)
    assert indexer.index_file(f) == 0
    assert store.count() == 0


def test_reindex_replaces_old_chunks(tmp_path: Path) -> None:
    f = tmp_path / "evolving.md"
    f.write_text("V1 contenu initial", encoding="utf-8")
    store, indexer = _indexer(tmp_path)
    indexer.index_file(f)
    assert store.count() == 1

    f.write_text("V2 contenu nouveau, complètement différent", encoding="utf-8")
    indexer.index_file(f)
    # Toujours 1 chunk (ancien remplacé)
    assert store.count() == 1
    facts = store.all_with_embeddings()
    assert "V2" in facts[0].text
    assert "V1" not in facts[0].text


# ---------------------------------------------------------------------------
# DocIndexer.scan_directory
# ---------------------------------------------------------------------------


def test_scan_directory_indexes_files(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("doc A", encoding="utf-8")
    (tmp_path / "b.md").write_text("doc B", encoding="utf-8")
    (tmp_path / "ignore.png").write_text("(binary)", encoding="utf-8")
    store, indexer = _indexer(tmp_path)
    res = indexer.scan_directory(tmp_path)
    assert res.files_scanned == 2
    assert res.chunks_created == 2
    assert store.count() == 2


def test_scan_skips_blacklisted_dirs(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.md").write_text("git internal", encoding="utf-8")
    (tmp_path / "good.md").write_text("contenu utile", encoding="utf-8")
    store, indexer = _indexer(tmp_path)
    res = indexer.scan_directory(tmp_path)
    assert res.files_scanned == 1
    assert store.count() == 1


def test_scan_skips_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "huge.md").write_text("X" * 1000, encoding="utf-8")
    (tmp_path / "ok.md").write_text("petit", encoding="utf-8")
    _store, indexer = _indexer(tmp_path, max_file_size_bytes=500)
    res = indexer.scan_directory(tmp_path)
    assert res.files_skipped == 1
    assert res.files_scanned == 1


def test_scan_nonexistent_root_returns_empty(tmp_path: Path) -> None:
    _, indexer = _indexer(tmp_path)
    res = indexer.scan_directory(tmp_path / "nope")
    assert res.files_scanned == 0


# ---------------------------------------------------------------------------
# End-to-end : indexation + retrieval
# ---------------------------------------------------------------------------


def test_search_after_indexing_finds_doc(tmp_path: Path) -> None:
    """E2E : indexation + reader.search retourne les chunks doc filtrés par kind."""
    f = tmp_path / "doc.md"
    f.write_text("contenu de test pour l'indexation E2E", encoding="utf-8")
    store = MemoryStore(tmp_path / "rag.db")
    embedder = HashEmbedder()
    DocIndexer(store, embedder).index_file(f)
    reader = MemoryReader(store, embedder)
    # HashEmbedder n'a pas de sémantique, mais le self-match doit donner score 1.0
    results = reader.search(
        "contenu de test pour l'indexation E2E",
        top_k=5,
        kind="doc_chunk",
    )
    assert len(results) >= 1
    assert results[0].score > 0.99  # self-match du chunk unique
    assert results[0].fact.kind == "doc_chunk"
    assert results[0].fact.source.endswith("doc.md")
