"""Routeur LLM hybride local/cloud.

Décide pour chaque requête si on envoie à Ollama local (rapide, gratuit, moins
capable) ou à Anthropic cloud (lent, payant, plus capable).

Heuristiques initiales (S2 affinera) :
- prompts courts + intents simples → local (Qwen 14B suffit largement)
- prompts longs OU intents complexes (reasoning, code, multi-tool) → cloud Sonnet 4.6
- ratio coût/qualité ajustable via seuils
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


class LlmRouter:
    """Routeur hybride entre Ollama local et Anthropic cloud.

    Stateless — la décision dépend uniquement des inputs (prompt + intent).
    """

    def __init__(
        self,
        *,
        cloud_threshold_tokens: int = CLOUD_PROMPT_TOKENS_THRESHOLD,
    ) -> None:
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

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)
