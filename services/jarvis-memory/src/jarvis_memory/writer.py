"""MemoryWriter : extrait des faits depuis un texte / une conversation et les stocke.

Pour le MVP, l'extraction est **heuristique** (regex sur formulations explicites
genre "je préfère X" / "rappelle-toi Y" / "j'utilise Z") plutôt que LLM-based.
L'extraction LLM-based viendra plus tard (Sprint mémoire avancée).

Évite les doublons via `MemoryStore.find_by_text`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from jarvis_memory.embedder import Embedder
from jarvis_memory.store import Fact, MemoryStore

# Quelques patterns d'expressions explicites de faits qui valent la peine d'être retenus.
_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brappelle-?toi (?:que )?(.+?)(?:\.|$)", "user_directive"),
    (r"\b(?:je suis|j'?ai|j'?habite|j'?utilise|je préfère|j'?aime) (.+?)(?:\.|,|$)", "biography"),
    (r"\bn'?oublie pas (?:que )?(.+?)(?:\.|$)", "user_directive"),
    (r"\bmon (?:mot de passe|adresse|email|numéro) (?:est|=) (.+?)(?:\.|$)", "credential"),
)


@dataclass(frozen=True, slots=True)
class WriteResult:
    fact_id: int
    fact: Fact
    duplicate: bool


class MemoryWriter:
    """Décide ce qui mérite d'être retenu + persiste avec embedding."""

    def __init__(
        self,
        store: MemoryStore,
        embedder: Embedder,
        *,
        skip_kinds: tuple[str, ...] = ("credential",),
    ) -> None:
        """Args:
        store: MemoryStore où persister.
        embedder: Embedder utilisé pour calculer le vecteur.
        skip_kinds: kinds qu'on REFUSE d'écrire (par défaut "credential" pour
            éviter de stocker un mot de passe en clair, même heuristique).
        """
        self.store = store
        self.embedder = embedder
        self.skip_kinds = set(skip_kinds)

    def add_fact(
        self,
        text: str,
        *,
        kind: str = "user_directive",
        source: str = "session",
        metadata: dict | None = None,
        skip_if_duplicate: bool = True,
    ) -> WriteResult | None:
        """Ajoute un fait au store. Retourne None si refusé (kind blocké)."""
        text = text.strip()
        if not text:
            return None
        if kind in self.skip_kinds:
            return None
        if skip_if_duplicate and self.store.find_by_text(text):
            existing = self.store.find_by_text(text)[0]
            return WriteResult(fact_id=existing.id, fact=existing, duplicate=True)
        embedding = self.embedder.embed(text)
        fact = Fact(
            id=None,
            ts=time.time(),
            kind=kind,
            text=text,
            source=source,
            metadata=metadata or {},
            embedding=embedding,
        )
        fact_id = self.store.add(fact)
        return WriteResult(
            fact_id=fact_id,
            fact=Fact(
                id=fact_id,
                ts=fact.ts,
                kind=fact.kind,
                text=fact.text,
                source=fact.source,
                metadata=fact.metadata,
                embedding=fact.embedding,
            ),
            duplicate=False,
        )

    def extract_from_text(self, text: str, *, source: str = "session") -> list[WriteResult]:
        """Cherche des faits explicites dans `text` (regex heuristique) et les stocke."""
        results: list[WriteResult] = []
        for pattern, kind in _PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                captured = match.group(1).strip()
                if not captured or len(captured) < 3:
                    continue
                fact_text = self._normalize(kind, captured)
                wr = self.add_fact(fact_text, kind=kind, source=source)
                if wr is not None:
                    results.append(wr)
        return results

    @staticmethod
    def _normalize(kind: str, captured: str) -> str:
        """Préfixe avec le kind pour rendre le fait plus auto-explicatif au recall."""
        if kind == "biography":
            return f"L'utilisateur {captured}"
        if kind == "user_directive":
            return f"Directive : {captured}"
        return captured
