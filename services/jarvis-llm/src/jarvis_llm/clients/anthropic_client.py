"""Wrapper Anthropic API pour Jarvis (LLM cloud Sonnet 4.6).

Skeleton S2 — interface fixée ici, implémentation réelle (streaming, prompt caching,
gestion des outils, observability LangSmith) au sprint S2.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CLOUD_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True, slots=True)
class AnthropicCompletion:
    """Résultat d'une complétion Anthropic."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class AnthropicClient:
    """Client async vers l'API Anthropic.

    Args:
        api_key: clé API Anthropic. À récupérer via `keyring.get_password("jarvis",
            "anthropic_api_key")` plutôt qu'un .env (cf README sécurité).
        model: ID du modèle (défaut claude-sonnet-4-6).
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_CLOUD_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicClient: api_key requis (utilise keyring, pas .env).")
        self.api_key = api_key
        self.model = model

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> AnthropicCompletion:
        """Génère une complétion non-streaming via l'API Messages.

        Implémentation réelle au sprint S2 — pour l'instant lève NotImplementedError.
        """
        raise NotImplementedError("AnthropicClient.complete() arrive au sprint S2 (1er juin 2026).")
