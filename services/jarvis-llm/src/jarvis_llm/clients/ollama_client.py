"""Wrapper Ollama pour Jarvis (seul backend LLM — 100% local).

Implémentation non-streaming via `ollama.AsyncClient`. Streaming arrivera au
sprint Voice (S3-S4) quand le pipeline Pipecat aura besoin de tokens-as-they-come.

Modèle par défaut : `qwen2.5:14b-instruct-q4_K_M` (équilibre chat + code,
9 GB Q4 tient entièrement en VRAM RTX 5070 Ti 16 GB, ~15 tok/s steady).
Alternatives testées : `gpt-oss:120b` (top qualité mais offload partiel,
~9 tok/s). Override possible via la variable d'env `JARVIS_LLM_MODEL`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import ollama

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_LOCAL_MODEL = os.environ.get("JARVIS_LLM_MODEL", "qwen2.5:14b-instruct-q4_K_M")


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
        host: URL du serveur Ollama (défaut http://127.0.0.1:11434, override via $OLLAMA_HOST).
        model: nom du modèle à utiliser (défaut gpt-oss:120b, override via $JARVIS_LLM_MODEL).
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_LOCAL_MODEL,
    ) -> None:
        self.host = host
        self.model = model
        self._client = ollama.AsyncClient(host=host)

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> OllamaCompletion:
        """Génère une complétion non-streaming pour le prompt donné.

        Args:
            prompt: message utilisateur.
            max_tokens: limite de tokens en sortie (mappé sur `num_predict` côté Ollama).
            system: prompt système optionnel.

        Returns:
            OllamaCompletion avec le texte + comptage tokens (depuis prompt_eval_count
            et eval_count retournés par Ollama).

        Raises:
            ollama.ResponseError: erreur API Ollama (ex: modèle pas pulled).
            httpx.ConnectError: serveur Ollama injoignable.
        """
        messages = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat(
            model=self.model,
            messages=messages,
            options={"num_predict": max_tokens},
            stream=False,
        )

        return OllamaCompletion(
            text=response["message"]["content"],
            model=response.get("model", self.model),
            prompt_tokens=int(response.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(response.get("eval_count", 0) or 0),
        )
