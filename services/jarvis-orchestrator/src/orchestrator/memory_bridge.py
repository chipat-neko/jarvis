"""Pont entre Conversation et jarvis-memory (writer + reader).

Logique :
- À chaque nouveau message user, on cherche des facts pertinents via le reader
  et on injecte un mini-paragraphe au system prompt → le LLM voit "tu sais que…"
- Après chaque réponse (ou périodiquement), on lance le writer sur le dernier
  message user pour capturer les directives / préférences explicites.

Le bridge est OPTIONNEL et désactivable : si on n'a pas de memory store, le
chat tourne exactement comme avant.
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_memory.reader import MemoryReader
from jarvis_memory.writer import MemoryWriter

DEFAULT_RECALL_TOP_K = 3
DEFAULT_RECALL_MIN_SCORE = 0.30  # cosine en dessous = bruit, on filtre
DEFAULT_MAX_INJECTED_CHARS = 800


@dataclass(frozen=True, slots=True)
class RecallInjection:
    """Texte à injecter dans le system prompt, + trace."""

    text: str  # paragraphe à concaténer après le system prompt ("" si rien à dire)
    facts_used: tuple[str, ...]  # textes des facts injectés (pour debug / display)


class MemoryBridge:
    """Pont orchestrator ↔ jarvis-memory.

    Args:
        writer: MemoryWriter pour persister les facts extraits.
        reader: MemoryReader pour recall sémantique.
        recall_top_k: nb max de facts à injecter par tour.
        recall_min_score: seuil de similarité (0..1) en-dessous duquel on ignore.
        max_injected_chars: limite caractères de l'injection (anti-spam tokens).
    """

    def __init__(
        self,
        *,
        writer: MemoryWriter,
        reader: MemoryReader,
        recall_top_k: int = DEFAULT_RECALL_TOP_K,
        recall_min_score: float = DEFAULT_RECALL_MIN_SCORE,
        max_injected_chars: int = DEFAULT_MAX_INJECTED_CHARS,
    ) -> None:
        self.writer = writer
        self.reader = reader
        self.recall_top_k = recall_top_k
        self.recall_min_score = recall_min_score
        self.max_injected_chars = max_injected_chars

    # ----- Recall (avant LLM call) -----

    def recall(self, user_msg: str) -> RecallInjection:
        """Cherche des facts pertinents pour `user_msg` et retourne un texte à injecter."""
        if not user_msg.strip():
            return RecallInjection(text="", facts_used=())
        results = self.reader.search(
            user_msg,
            top_k=self.recall_top_k,
            min_score=self.recall_min_score,
        )
        if not results:
            return RecallInjection(text="", facts_used=())
        # Construit le paragraphe (en français pour le system prompt)
        lines = ["Contexte mémoire (à utiliser si pertinent, sinon ignorer) :"]
        used: list[str] = []
        for r in results:
            line = f"- {r.fact.text}"
            # Stop si on déborde le budget caractères
            if sum(len(line_) for line_ in [*lines, line]) + 2 > self.max_injected_chars:
                break
            lines.append(line)
            used.append(r.fact.text)
        return RecallInjection(text="\n".join(lines), facts_used=tuple(used))

    def augment_system_prompt(self, base_system: str, user_msg: str) -> tuple[str, RecallInjection]:
        """Helper : retourne (system_prompt augmenté, trace de l'injection)."""
        injection = self.recall(user_msg)
        if not injection.text:
            return base_system, injection
        return f"{base_system}\n\n{injection.text}", injection

    # ----- Persist (après LLM call) -----

    def persist_from_user_message(self, user_msg: str, *, source: str = "session"):
        """Extrait des faits explicites du message user (heuristique regex)."""
        return self.writer.extract_from_text(user_msg, source=source)
