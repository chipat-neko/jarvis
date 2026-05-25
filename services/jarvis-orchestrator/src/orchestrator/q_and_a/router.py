"""Routeur d'intent Q/R : classifie un prompt et dispatche vers le bon answerer.

Heuristique simple basée sur mots-clés FR/EN (cf. recherche 103). Pas de LLM
ici — c'est le pré-filtre rapide AVANT d'appeler un LLM, pour répondre
directement sans tokens quand la question est "factuelle locale".

Le routeur ne fait QUE classifier ; les answerers sont injectés à l'extérieur
pour rester testables. Si l'intent est `none`, le caller doit fallback sur LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    """Catégorie d'intent détectée."""

    FILES = "files"
    GIT = "git"
    SYSTEM = "system"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class IntentMatch:
    """Résultat de classification."""

    intent: Intent
    confidence: float  # 0.0 à 1.0, indicatif (compte des matches normalisé)
    matched_keywords: tuple[str, ...] = ()


_KEYWORDS_FILES: tuple[str, ...] = (
    "fichier", "fichiers", "file", "files",
    "dossier", "dossiers", "folder", "folders", "directory",
    "trouve", "trouver", "find",
    "cherche", "chercher", "search",
    "grep",
    "lis", "lire", "read",
    "contenu",
    "ouvrir", "ouvre", "open",
    "code source",
)

_KEYWORDS_GIT: tuple[str, ...] = (
    "git",
    "commit", "commits",
    "branche", "branches", "branch",
    "diff",
    "status",
    "merge",
    "rebase",
    "pull request", "pr",
    "log",
    "checkout",
    "repo", "repository",
    "hash", "sha",
)

_KEYWORDS_SYSTEM: tuple[str, ...] = (
    "cpu", "processeur",
    "ram", "mémoire", "memory",
    "gpu", "carte graphique", "graphics card", "vram",
    "disque", "disk", "ssd",
    "process", "processus", "processes",
    "ollama",
    "système", "system",
    "charge",
    "temperature", "température", "temp",
    "nvidia",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _count_hits(text: str, keywords: tuple[str, ...]) -> tuple[int, tuple[str, ...]]:
    """Compte les keywords trouvés comme sous-chaîne dans `text` (déjà normalisé).

    On utilise des bordures de mot quand le keyword n'a pas d'espace, pour éviter
    qu'un "cpu" matche "cpuid" (faux positif).
    """
    hits: list[str] = []
    for kw in keywords:
        if " " in kw:
            if kw in text:
                hits.append(kw)
        elif re.search(rf"\b{re.escape(kw)}\b", text):
            hits.append(kw)
    return len(hits), tuple(hits)


class IntentRouter:
    """Classifieur d'intent par mots-clés.

    Args:
        threshold_min_hits: nombre minimal de matches pour activer un intent.
            En dessous → Intent.NONE.
    """

    def __init__(self, *, threshold_min_hits: int = 1) -> None:
        self.threshold_min_hits = max(1, threshold_min_hits)

    def classify(self, prompt: str) -> IntentMatch:
        if not prompt or not prompt.strip():
            return IntentMatch(intent=Intent.NONE, confidence=0.0)
        text = _normalize(prompt)

        scores: dict[Intent, tuple[int, tuple[str, ...]]] = {
            Intent.FILES: _count_hits(text, _KEYWORDS_FILES),
            Intent.GIT: _count_hits(text, _KEYWORDS_GIT),
            Intent.SYSTEM: _count_hits(text, _KEYWORDS_SYSTEM),
        }

        best_intent = Intent.NONE
        best_count = 0
        best_hits: tuple[str, ...] = ()
        for intent, (count, hits) in scores.items():
            if count > best_count:
                best_intent = intent
                best_count = count
                best_hits = hits

        if best_count < self.threshold_min_hits:
            return IntentMatch(intent=Intent.NONE, confidence=0.0)

        total_hits = sum(c for c, _ in scores.values())
        confidence = round(best_count / total_hits, 3) if total_hits else 0.0
        return IntentMatch(
            intent=best_intent,
            confidence=confidence,
            matched_keywords=best_hits,
        )
