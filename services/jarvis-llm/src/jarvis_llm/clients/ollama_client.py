"""Wrapper Ollama pour Jarvis (LLM local Qwen 14B).

Skeleton S2 — l'interface est fixée ici, l'implémentation réelle (streaming, prompt
caching côté Ollama, gestion du context window) sera complétée au sprint S2.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "qwen2.5:14b-instruct-q4_K_M"


@dataclass(frozen=True, slots=True)
class OllamaCompletion:
    """Résultat brut d'une complétion Ollama."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class OllamaClient:
    """Client async vers une instance Ollama locale.

    Args:
        host: URL du serveur Ollama (défaut http://127.0.0.1:11434).
        model: nom du modèle à utiliser (défaut Qwen 14B Q4 instruct).
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_LOCAL_MODEL,
    ) -> None:
        self.host = host
        self.model = model

    async def complete(self, prompt: str, *, max_tokens: int = 512) -> OllamaCompletion:
        """Génère une complétion non-streaming pour le prompt donné.

        Implémentation réelle au sprint S2 — pour l'instant lève NotImplementedError
        afin que tout appelant sache que cette voie n'est pas encore branchée.
        """
        raise NotImplementedError("OllamaClient.complete() arrive au sprint S2 (1er juin 2026).")
