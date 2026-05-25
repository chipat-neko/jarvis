"""MemoryReader : retrieval par similarité sémantique (cosinus en Python pur)."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_memory.embedder import Embedder, cosine_similarity
from jarvis_memory.store import Fact, MemoryStore


@dataclass(frozen=True, slots=True)
class Recall:
    """Un fact recallé, avec son score de similarité."""

    fact: Fact
    score: float


class MemoryReader:
    """Recherche sémantique top-k sur les facts stockés."""

    def __init__(self, store: MemoryStore, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        kind: str | None = None,
        min_score: float = 0.0,
    ) -> list[Recall]:
        """Retourne les `top_k` facts les plus similaires à `query`.

        Args:
            query: texte de requête.
            top_k: nombre max de résultats.
            kind: si fourni, filtre sur ce kind.
            min_score: ignore les résultats sous ce seuil de similarité.
        """
        if not query.strip():
            return []
        query_vec = self.embedder.embed(query)
        candidates = self.store.all_with_embeddings(kind=kind)
        scored: list[Recall] = []
        for fact in candidates:
            if not fact.embedding:
                continue
            score = cosine_similarity(query_vec, fact.embedding)
            if score < min_score:
                continue
            scored.append(Recall(fact=fact, score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
