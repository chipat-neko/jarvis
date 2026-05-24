"""Routeur LLM hybride local/cloud.

Décide pour chaque requête si on envoie à Ollama local (rapide, gratuit, moins
capable) ou à Anthropic cloud (lent, payant, plus capable), puis exécute l'appel.

Heuristiques initiales (S2 affinera) :
- prompts courts + intents simples → local (Qwen 14B suffit largement)
- prompts longs OU intents complexes (reasoning, code, multi-tool) → cloud Sonnet 4.6
- ratio coût/qualité ajustable via seuils
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jarvis_llm.clients.anthropic_client import AnthropicClient
from jarvis_llm.clients.ollama_client import OllamaClient

# Au-delà de ce nombre de tokens estimés dans le prompt, on bascule au cloud.
# Qwen 14B accepte ~32k tokens mais sa qualité chute fort après ~4k tokens en pratique.
CLOUD_PROMPT_TOKENS_THRESHOLD = 2000

# Heuristique simpliste : ~4 caractères = 1 token pour FR/EN mixte.
CHARS_PER_TOKEN_ESTIMATE = 4


class IntentClass(StrEnum):
    """Classification grossière de l'intent de l'utilisateur.

    Sert au routing : les intents simples peuvent aller en local, les complexes
    bénéficient du cloud (meilleur reasoning).
    """

    SIMPLE = "simple"  # FAQ, status, météo, conversion → local
    CONVERSATIONAL = "conversational"  # discussion fluide → local
    COMPLEX = "complex"  # reasoning, multi-step → cloud
    CODE = "code"  # génération/explication code → cloud
    TOOL_USE = "tool_use"  # appel d'outils multiples → cloud


class RouteTarget(StrEnum):
    """Cible de routing décidée par le router."""

    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Décision du routeur pour une requête donnée."""

    target: RouteTarget
    reason: str
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Résultat d'un appel LLM, agnostique du backend (local ou cloud)."""

    text: str
    target: RouteTarget
    model: str
    input_tokens: int
    output_tokens: int
    reason: str


class LlmRouter:
    """Routeur hybride entre Ollama local et Anthropic cloud.

    Stateless côté décision — l'exécution dépend des clients injectés.

    Args:
        anthropic_client: client cloud. Si None, toute requête cloud sera rejetée.
        ollama_client: client local. Si None, toute requête locale fallback au cloud
            (ou échoue si pas de cloud non plus).
        cloud_threshold_tokens: au-delà, on bascule au cloud même pour intent simple.
    """

    def __init__(
        self,
        *,
        anthropic_client: AnthropicClient | None = None,
        ollama_client: OllamaClient | None = None,
        cloud_threshold_tokens: int = CLOUD_PROMPT_TOKENS_THRESHOLD,
    ) -> None:
        self.anthropic_client = anthropic_client
        self.ollama_client = ollama_client
        self.cloud_threshold_tokens = cloud_threshold_tokens

    def decide(self, prompt: str, intent: IntentClass) -> RouteDecision:
        """Retourne la cible (local/cloud) pour le prompt + intent donnés."""
        estimated_tokens = self._estimate_tokens(prompt)

        if intent in {IntentClass.COMPLEX, IntentClass.CODE, IntentClass.TOOL_USE}:
            return RouteDecision(
                target=RouteTarget.CLOUD,
                reason=f"intent={intent.value} requiert cloud Sonnet 4.6",
                estimated_tokens=estimated_tokens,
            )

        if estimated_tokens > self.cloud_threshold_tokens:
            return RouteDecision(
                target=RouteTarget.CLOUD,
                reason=(
                    f"prompt ~{estimated_tokens} tokens > seuil "
                    f"{self.cloud_threshold_tokens} → cloud"
                ),
                estimated_tokens=estimated_tokens,
            )

        return RouteDecision(
            target=RouteTarget.LOCAL,
            reason=f"intent={intent.value} + prompt court → local Qwen 14B",
            estimated_tokens=estimated_tokens,
        )

    async def execute(
        self,
        prompt: str,
        intent: IntentClass,
        *,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> CompletionResult:
        """Décide + exécute l'appel LLM. Fallback cloud si local indispo.

        Args:
            prompt: message utilisateur.
            intent: classification de la requête.
            max_tokens: limite tokens en sortie.
            system: prompt système optionnel.

        Returns:
            CompletionResult uniforme quel que soit le backend.

        Raises:
            RuntimeError: si aucun client n'est disponible pour la cible décidée.
        """
        decision = self.decide(prompt, intent)
        target = decision.target

        if target is RouteTarget.LOCAL and self.ollama_client is None:
            if self.anthropic_client is None:
                raise RuntimeError("Aucun client LLM disponible (ni local, ni cloud).")
            target = RouteTarget.CLOUD
            reason = f"{decision.reason} → fallback cloud (Ollama indispo)"
        elif target is RouteTarget.CLOUD and self.anthropic_client is None:
            if self.ollama_client is None:
                raise RuntimeError("Aucun client LLM disponible (ni local, ni cloud).")
            target = RouteTarget.LOCAL
            reason = f"{decision.reason} → fallback local (clé Anthropic absente)"
        else:
            reason = decision.reason

        if target is RouteTarget.LOCAL:
            assert self.ollama_client is not None  # garanti par le bloc ci-dessus
            local = await self.ollama_client.complete(prompt, max_tokens=max_tokens, system=system)
            return CompletionResult(
                text=local.text,
                target=RouteTarget.LOCAL,
                model=local.model,
                input_tokens=local.prompt_tokens,
                output_tokens=local.completion_tokens,
                reason=reason,
            )

        assert self.anthropic_client is not None  # garanti par le bloc ci-dessus
        cloud = await self.anthropic_client.complete(prompt, max_tokens=max_tokens, system=system)
        return CompletionResult(
            text=cloud.text,
            target=RouteTarget.CLOUD,
            model=cloud.model,
            input_tokens=cloud.input_tokens,
            output_tokens=cloud.output_tokens,
            reason=reason,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)
