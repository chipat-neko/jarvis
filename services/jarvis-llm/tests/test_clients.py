"""Tests du wrapper Ollama avec mock (pas d'appel réseau)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from jarvis_llm.clients.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_ollama_complete_maps_chat_response() -> None:
    fake_response = {
        "message": {"content": "salut, ça va !"},
        "model": "gpt-oss:120b",
        "prompt_eval_count": 8,
        "eval_count": 5,
    }

    with patch("ollama.AsyncClient") as mock_class:
        mock_class.return_value.chat = AsyncMock(return_value=fake_response)
        client = OllamaClient(model="gpt-oss:120b")
        result = await client.complete("Salut", system="Tu es Jarvis")

    assert result.text == "salut, ça va !"
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 5
    assert result.model == "gpt-oss:120b"


@pytest.mark.asyncio
async def test_ollama_complete_handles_missing_token_counts() -> None:
    fake_response = {
        "message": {"content": "ok"},
        # ni prompt_eval_count ni eval_count → on doit retomber à 0
    }

    with patch("ollama.AsyncClient") as mock_class:
        mock_class.return_value.chat = AsyncMock(return_value=fake_response)
        client = OllamaClient(model="any")
        result = await client.complete("Hi")

    assert result.text == "ok"
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
