"""Wrapper Ollama pour Jarvis (seul backend LLM — 100% local).

Implémentation non-streaming via `ollama.AsyncClient`. Streaming arrivera au
sprint Voice (S3-S4) quand le pipeline Pipecat aura besoin de tokens-as-they-come.

Modèle par défaut : `qwen3:14b` (génération Qwen 3, ~9 GB Q4 tient en VRAM
16 GB, ~31 tok/s steady avec `think=False`, qualité au-dessus de Qwen 2.5
sur les mêmes 10 prompts hard E2E). Alternatives testées :
- `qwen2.5:14b-instruct-q4_K_M` (15 tok/s, 1 erreur arithmétique observée)
- `gpt-oss:120b` (9 tok/s steady, top qualité mais 2 min de cold start)
Override possible via la variable d'env `JARVIS_LLM_MODEL`.

NOTE thinking models : Qwen 3, DeepSeek-R1 et autres "thinking models" génèrent
des tokens de raisonnement interne (`<think>...</think>`) qui consomment le
budget `max_tokens` avant la vraie réponse. On désactive le thinking par défaut
pour avoir des réponses directes utilisables. Activable via `think=True` au
constructeur si l'utilisateur veut le raisonnement étape par étape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import ollama

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_LOCAL_MODEL = os.environ.get("JARVIS_LLM_MODEL", "qwen3:14b")


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
        model: nom du modèle à utiliser (défaut qwen2.5:14b-instruct-q4_K_M,
            override via $JARVIS_LLM_MODEL).
        think: pour les thinking models (Qwen3, DeepSeek-R1…), True active le
            raisonnement interne `<think>...</think>` qui consomme du budget tokens
            avant la vraie réponse. False (défaut) demande la réponse directe.
            Sur un modèle non-thinking, le param est ignoré côté Ollama.
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_LOCAL_MODEL,
        think: bool = False,
    ) -> None:
        self.host = host
        self.model = model
        self.think = think
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
            think=self.think,
            stream=False,
        )

        return OllamaCompletion(
            text=response["message"]["content"],
            model=response.get("model", self.model),
            prompt_tokens=int(response.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(response.get("eval_count", 0) or 0),
        )
