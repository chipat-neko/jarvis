"""Helpers pour câbler MemoryBridge dans le REPL chat.

Sortis dans un module séparé pour garder `chat.py` lisible. La mémoire est
optionnelle : si `jarvis-memory` n'est pas installé ou si le user ne passe pas
`--enable-memory`, le REPL fonctionne exactement comme avant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_MEMORY_DB = Path(".local/memory.db")
DEFAULT_EMBEDDER_KIND = "hash"  # "hash" | "bge"


@dataclass
class MemoryStack:
    """Pack des composants memory utilisés dans le REPL."""

    bridge: object  # MemoryBridge (typed object pour pas dépendre dur de jarvis-memory)
    store: object  # MemoryStore


def build_memory_stack(
    *,
    db_path: str | Path = DEFAULT_MEMORY_DB,
    embedder_kind: str = DEFAULT_EMBEDDER_KIND,
) -> MemoryStack | None:
    """Construit MemoryStore + Embedder + Writer + Reader + Bridge.

    Retourne None si `jarvis-memory` n'est pas installé ou si l'embedder ML
    demandé n'a pas ses deps. Permet au REPL de tomber gracieusement en
    "pas de mémoire" sans crasher.
    """
    try:
        from jarvis_memory.embedder import (  # noqa: PLC0415
            HashEmbedder,
            SentenceTransformerEmbedder,
        )
        from jarvis_memory.reader import MemoryReader  # noqa: PLC0415
        from jarvis_memory.store import MemoryStore  # noqa: PLC0415
        from jarvis_memory.writer import MemoryWriter  # noqa: PLC0415
        from orchestrator.memory_bridge import MemoryBridge  # noqa: PLC0415
    except ImportError:
        return None

    store = MemoryStore(Path(db_path))
    if embedder_kind == "bge":
        try:
            embedder = SentenceTransformerEmbedder()
            # Force le chargement du modèle pour échouer ici plutôt que au 1er call
            _ = embedder.dim
        except RuntimeError:
            return None
    else:
        embedder = HashEmbedder()

    writer = MemoryWriter(store, embedder)
    reader = MemoryReader(store, embedder)
    bridge = MemoryBridge(writer=writer, reader=reader)
    return MemoryStack(bridge=bridge, store=store)


def memory_list(stack: MemoryStack, *, limit: int = 20) -> str:
    """Liste les N derniers facts persistés (commande /memory)."""
    from jarvis_memory.store import MemoryStore  # noqa: PLC0415

    store: MemoryStore = stack.store  # type: ignore[assignment]
    total = store.count()
    if total == 0:
        return "(aucun fait persisté)"

    # Pas d'API "recent" dédiée → on lit la table directement.
    with store._lock, store._connect() as conn:
        rows = conn.execute(
            "SELECT id, ts, kind, text, source FROM facts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    lines = [f"🧠 {total} faits en mémoire (les {min(total, limit)} plus récents) :"]
    for row in rows:
        fid, _ts, kind, text, source = row
        preview = text if len(text) <= 80 else text[:77] + "…"
        lines.append(f"   #{fid} [{kind}/{source}] {preview}")
    return "\n".join(lines)


def memory_clear(stack: MemoryStack) -> str:
    """Vide tous les faits (commande /memory clear)."""
    from jarvis_memory.store import MemoryStore  # noqa: PLC0415

    store: MemoryStore = stack.store  # type: ignore[assignment]
    with store._lock, store._connect() as conn:
        before = int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
        conn.execute("DELETE FROM facts")
        conn.commit()
    return f"✅ {before} fait(s) effacé(s)."


def augment_messages(stack: MemoryStack, messages: list[dict], user_msg: str) -> list[dict]:
    """Augmente le system message des `messages` avec le recall du bridge.

    Retourne une NOUVELLE liste (pas de mutation in-place).
    """
    if not messages:
        return messages
    bridge = stack.bridge  # type: ignore[attr-defined]
    head = messages[0]
    if head.get("role") != "system":
        return messages
    augmented, _ = bridge.augment_system_prompt(head.get("content", ""), user_msg)
    if augmented == head.get("content"):
        return messages
    return [{"role": "system", "content": augmented}, *messages[1:]]
