"""Tests du wiring chat_memory : build_memory_stack + augment + commandes."""

from __future__ import annotations

from pathlib import Path

from orchestrator.chat_memory import (
    augment_messages,
    build_memory_stack,
    memory_clear,
    memory_list,
)


def test_build_memory_stack_hash_embedder(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    assert stack.store is not None
    assert stack.bridge is not None


def test_build_memory_stack_persists_db(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    stack = build_memory_stack(db_path=db, embedder_kind="hash")
    assert stack is not None
    # Ajoute un fact via le bridge writer, vérifie qu'il atterrit dans le db
    results = stack.bridge.persist_from_user_message(  # type: ignore[attr-defined]
        "Rappelle-toi que je préfère les réponses courtes."
    )
    assert len(results) >= 1
    assert db.exists()
    assert db.stat().st_size > 0


def test_memory_list_empty(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    out = memory_list(stack)
    assert "aucun" in out.lower()


def test_memory_list_after_persist(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    stack.bridge.persist_from_user_message(  # type: ignore[attr-defined]
        "Rappelle-toi que je travaille sur Jarvis."
    )
    out = memory_list(stack)
    assert "1 faits" in out
    assert "Jarvis" in out


def test_memory_list_truncates_long_texts(tmp_path: Path) -> None:
    from jarvis_memory.embedder import HashEmbedder
    from jarvis_memory.store import Fact, MemoryStore

    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    store: MemoryStore = stack.store  # type: ignore[assignment]
    store.add(
        Fact(
            id=None,
            ts=0,
            kind="biography",
            text="A" * 200,
            embedding=HashEmbedder().embed("anything"),
        )
    )
    out = memory_list(stack)
    assert "…" in out  # ellipsis présente


def test_memory_clear(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    stack.bridge.persist_from_user_message(  # type: ignore[attr-defined]
        "Rappelle-toi que je travaille tard."
    )
    out = memory_clear(stack)
    assert "1 fait" in out
    assert "effacé" in out
    # Le store est vide après clear
    assert memory_list(stack).lower().startswith("(aucun")


def test_augment_messages_no_system_returns_input(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    messages = [{"role": "user", "content": "salut"}]
    out = augment_messages(stack, messages, "salut")
    assert out == messages  # pas de system → pas de modif


def test_augment_messages_no_facts_returns_input(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    messages = [
        {"role": "system", "content": "Tu es Jarvis."},
        {"role": "user", "content": "salut"},
    ]
    out = augment_messages(stack, messages, "salut")
    assert out == messages  # store vide → rien à recall


def test_augment_messages_injects_facts(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    persisted = stack.bridge.persist_from_user_message(  # type: ignore[attr-defined]
        "Rappelle-toi que je préfère le café noir."
    )
    fact_text = persisted[0].fact.text
    messages = [
        {"role": "system", "content": "Tu es Jarvis."},
        {"role": "user", "content": fact_text},
    ]
    out = augment_messages(stack, messages, fact_text)
    assert out is not messages
    assert "Tu es Jarvis." in out[0]["content"]
    assert "Contexte mémoire" in out[0]["content"]
    assert "café noir" in out[0]["content"]


def test_augment_messages_empty_input(tmp_path: Path) -> None:
    stack = build_memory_stack(db_path=tmp_path / "mem.db", embedder_kind="hash")
    assert stack is not None
    assert augment_messages(stack, [], "anything") == []
