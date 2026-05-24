"""Routeur LLM 100% local (Ollama).

Une seule cible : Ollama. Pas de cloud, pas de clé API, pas de fuite de données.
Le routing "intelligent" se limite pour l'instant à de l'observability (on conserve
la classification d'intent pour le logging et un futur routing multi-modèles).

À terme, on pourra charger plusieurs modèles dans Ollama (un petit rapide pour
le smalltalk, un gros capable pour le code) et router selon l'intent. Pour le
MVP, un seul modèle (gpt-oss:120b par défaut).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jarvis_llm.clients.ollama_client import OllamaClient

# Heuristique simpliste : ~4 caractères = 1 token pour FR/EN mixte.
# Utilisé uniquement pour l'observability (estimation pré-call).
CHARS_PER_TOKEN_ESTIMATE = 4


class IntentClass(StrEnum):
    """Classification grossière de l'intent de l'utilisateur.

    Sert pour l'observability (logging) et potentiellement un futur routing
    multi-modèles (S2+). Pour l'instant, tous les intents tapent le même modèle.
    """

    SIMPLE = "simple"  # FAQ, status, météo, conversion
    CONVERSATIONAL = "conversational"  # discussion fluide
    COMPLEX = "complex"  # reasoning, multi-step
    CODE = "code"  # génération/explication code
    TOOL_USE = "tool_use"  # appel d'outils multiples (S5+, MCP)


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Résultat d'un appel LLM local."""

    text: str
    model: str
    intent: IntentClass
    input_tokens: int
    output_tokens: int
    estimated_prompt_tokens: int


class LlmRouter:
    """Routeur LLM 100% local.

    Args:
        ollama_client: client local Ollama. Requis.
    """

    def __init__(self, *, ollama_client: OllamaClient) -> None:
        if ollama_client is None:
            raise ValueError("LlmRouter: ollama_client requis (100% local, pas de cloud).")
        self.ollama_client = ollama_client

    async def execute(
        self,
        prompt: str,
        intent: IntentClass,
        *,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> CompletionResult:
        """Exécute l'appel LLM local.

        Args:
            prompt: message utilisateur.
            intent: classification (loggée mais ne change pas la cible pour l'instant).
            max_tokens: limite tokens en sortie.
            system: prompt système optionnel.

        Returns:
            CompletionResult avec texte + comptage tokens + intent loggé.

        Raises:
            ollama.ResponseError / httpx.ConnectError: si Ollama injoignable ou modèle pas pulled.
        """
        estimated = self._estimate_tokens(prompt)
        completion = await self.ollama_client.complete(prompt, max_tokens=max_tokens, system=system)
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
