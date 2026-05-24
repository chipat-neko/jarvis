"""Routeur LLM 100% local (Ollama ou HuggingFace `transformers`).

Pas de cloud, pas de clé API, pas de fuite de données. Le routing "intelligent"
se limite pour l'instant à de l'observability (on conserve la classification
d'intent pour le logging et un futur routing multi-modèles).

À terme, on pourra avoir plusieurs backends en parallèle (gros modèle pour code,
petit modèle rapide pour smalltalk) et router selon l'intent. Pour le MVP, un
seul backend (Ollama par défaut, HF en alternative).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

# Heuristique simpliste : ~4 caractères = 1 token pour FR/EN mixte.
# Utilisé uniquement pour l'observability (estimation pré-call).
CHARS_PER_TOKEN_ESTIMATE = 4


class IntentClass(StrEnum):
    """Classification grossière de l'intent de l'utilisateur.

    Sert pour l'observability (logging) et potentiellement un futur routing
    multi-modèles. Pour l'instant, tous les intents tapent le même backend.
    """

    SIMPLE = "simple"
    CONVERSATIONAL = "conversational"
    COMPLEX = "complex"
    CODE = "code"
    TOOL_USE = "tool_use"


class _BackendCompletion(Protocol):
    """Shape attendue d'un objet retourné par n'importe quel backend LLM."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


@runtime_checkable
class LlmBackend(Protocol):
    """Interface d'un backend LLM (Ollama, HuggingFace, ou tout futur ajout).

    Doit exposer un attribut `.model` (nom du modèle utilisé) et une méthode
    async `.complete(prompt, *, max_tokens, system) -> _BackendCompletion`.
    """

    model: str

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = ...,
        system: str | None = ...,
    ) -> _BackendCompletion: ...


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Résultat d'un appel LLM, agnostique du backend."""

    text: str
    model: str
    intent: IntentClass
    input_tokens: int
    output_tokens: int
    estimated_prompt_tokens: int


class LlmRouter:
    """Routeur LLM 100% local.

    Args:
        backend: backend LLM (OllamaClient, HuggingFaceClient, …). Requis.
    """

    def __init__(self, *, backend: LlmBackend) -> None:
        if backend is None:
            raise ValueError("LlmRouter: backend requis.")
        self.backend = backend

    async def execute(
        self,
        prompt: str,
        intent: IntentClass,
        *,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> CompletionResult:
        """Exécute l'appel LLM via le backend configuré."""
        estimated = self._estimate_tokens(prompt)
        completion = await self.backend.complete(prompt, max_tokens=max_tokens, system=system)
        return CompletionResult(
            text=completion.text,
            model=completion.model,
            intent=intent,
            input_tokens=completion.prompt_tokens,
            output_tokens=completion.completion_tokens,
            estimated_prompt_tokens=estimated,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)
