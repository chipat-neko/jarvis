"""Wrapper Anthropic API pour Jarvis (LLM cloud Sonnet 4.6).

Implémentation non-streaming. Streaming + prompt caching avancé + tool use
arriveront aux sprints suivants (S5+).
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

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
        api_key: clé API Anthropic. À récupérer via `jarvis_llm.secrets.get_anthropic_api_key()`
            (keyring Windows en priorité, env var en fallback). Ne JAMAIS hardcoder.
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
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> AnthropicCompletion:
        """Génère une complétion non-streaming via l'API Messages.

        Args:
            prompt: message utilisateur (rôle user).
            max_tokens: limite de tokens en sortie.
            system: prompt système optionnel (instructions persistantes).

        Returns:
            AnthropicCompletion avec le texte + comptage tokens.

        Raises:
            anthropic.APIError: erreur réseau ou API (propagée).
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        text = _extract_text(response)
        return AnthropicCompletion(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        )


def _extract_text(response: anthropic.types.Message) -> str:
    """Concatène les blocs de texte d'une réponse Messages API.

    L'API peut renvoyer plusieurs blocs (text, tool_use, ...). On ne garde que
    le texte pour ce MVP — tool_use sera géré au sprint MCP.
    """
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)
