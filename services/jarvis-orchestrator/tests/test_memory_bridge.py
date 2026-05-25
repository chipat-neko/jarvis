"""Tests du MemoryBridge : recall + augment + persist."""

from __future__ import annotations

from pathlib import Path

from jarvis_memory.embedder import HashEmbedder
from jarvis_memory.reader import MemoryReader
from jarvis_memory.store import MemoryStore
from jarvis_memory.writer import MemoryWriter
from orchestrator.memory_bridge import MemoryBridge


def _make_bridge(tmp_path: Path) -> tuple[MemoryBridge, MemoryWriter, MemoryReader]:
    store = MemoryStore(tmp_path / "mem.db")
    embedder = HashEmbedder()
    writer = MemoryWriter(store, embedder)
    reader = MemoryReader(store, embedder)
    bridge = MemoryBridge(writer=writer, reader=reader, recall_min_score=0.0)
    return bridge, writer, reader


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------


def test_recall_empty_when_no_facts(tmp_path: Path) -> None:
    bridge, _, _ = _make_bridge(tmp_path)
    injection = bridge.recall("any question")
    assert injection.text == ""
    assert injection.facts_used == ()


def test_recall_returns_self_match(tmp_path: Path) -> None:
    bridge, writer, _ = _make_bridge(tmp_path)
    writer.add_fact("L'utilisateur préfère le café noir")
    injection = bridge.recall("L'utilisateur préfère le café noir")
    assert injection.text != ""
    assert "café noir" in injection.text
    assert "L'utilisateur préfère le café noir" in injection.facts_used


def test_recall_filters_min_score(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    embedder = HashEmbedder()
    writer = MemoryWriter(store, embedder)
    reader = MemoryReader(store, embedder)
    bridge = MemoryBridge(writer=writer, reader=reader, recall_min_score=0.99)
    writer.add_fact("totalement non pertinent")
    # Score trop bas pour passer le filtre
    assert bridge.recall("question sans rapport").text == ""


def test_recall_respects_max_chars(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "mem.db")
    embedder = HashEmbedder()
    writer = MemoryWriter(store, embedder)
    reader = MemoryReader(store, embedder)
    bridge = MemoryBridge(
        writer=writer,
        reader=reader,
        recall_min_score=0.0,
        recall_top_k=20,
        max_injected_chars=200,
    )
    for i in range(20):
        writer.add_fact(f"fact assez long avec un peu de texte numéro {i} " * 3)
    injection = bridge.recall("fact")
    assert len(injection.text) <= 220  # léger overhead pour le header
    assert len(injection.facts_used) < 20  # tronqué pour respecter budget


def test_recall_empty_query(tmp_path: Path) -> None:
    bridge, writer, _ = _make_bridge(tmp_path)
    writer.add_fact("un fact")
    assert bridge.recall("").text == ""
    assert bridge.recall("   ").text == ""


# ---------------------------------------------------------------------------
# Augment
# ---------------------------------------------------------------------------


def test_augment_concatenates_when_injection_exists(tmp_path: Path) -> None:
    bridge, writer, _ = _make_bridge(tmp_path)
    writer.add_fact("Noah aime le café noir")
    base = "Tu es Jarvis, assistant concis."
    augmented, injection = bridge.augment_system_prompt(base, "Noah aime le café noir")
    assert base in augmented
    assert "Contexte mémoire" in augmented
    assert "café noir" in augmented
    assert injection.text != ""


def test_augment_returns_base_when_nothing_recalled(tmp_path: Path) -> None:
    bridge, _, _ = _make_bridge(tmp_path)
    base = "Tu es Jarvis."
    augmented, injection = bridge.augment_system_prompt(base, "rien à recall")
    assert augmented == base
    assert injection.text == ""


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------


def test_persist_extracts_directives(tmp_path: Path) -> None:
    bridge, _writer, _reader = _make_bridge(tmp_path)
    results = bridge.persist_from_user_message("Rappelle-toi que je préfère les réponses courtes.")
    assert len(results) >= 1
    # Le fact est dans le store
    assert any("réponses courtes" in r.fact.text for r in results)


def test_persist_does_not_throw_on_no_match(tmp_path: Path) -> None:
    bridge, _writer, _ = _make_bridge(tmp_path)
    bridge.persist_from_user_message("question quelconque sans pattern")
    # Pas d'exception levée == pass


def test_full_loop_save_then_recall(tmp_path: Path) -> None:
    """E2E : on persist un fact, puis on doit le retrouver via recall.

    Note : HashEmbedder n'est pas sémantique → on recall avec le TEXTE EXACT du
    fact persisté (qui passe par MemoryWriter._normalize pour les biography/
    user_directive). Pour la sémantique réelle, utiliser SentenceTransformerEmbedder.
    """
    bridge, _, _ = _make_bridge(tmp_path)
    persisted = bridge.persist_from_user_message(
        "Rappelle-toi que je travaille sur Jarvis le soir."
    )
    assert len(persisted) >= 1
    fact_text = persisted[0].fact.text
    injection = bridge.recall(fact_text)
    assert "Jarvis le soir" in injection.text
