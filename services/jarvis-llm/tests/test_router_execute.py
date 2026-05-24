"""Tests du LlmRouter.execute() avec client Ollama mocké."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from jarvis_llm.clients.ollama_client import OllamaCompletion
from jarvis_llm.router import IntentClass, LlmRouter


def _make_ollama_mock(text: str = "local-reply") -> AsyncMock:
    mock = AsyncMock()
    mock.complete = AsyncMock(
        return_value=OllamaCompletion(
            text=text,
            model="gpt-oss:120b",
            prompt_tokens=10,
            completion_tokens=4,
        )
    )
    return mock


@pytest.mark.asyncio
async def test_execute_calls_ollama_and_returns_completion_result() -> None:
    ollama = _make_ollama_mock("Bonjour, je suis Jarvis.")
    router = LlmRouter(backend=ollama)

    result = await router.execute("Salut", IntentClass.CONVERSATIONAL, system="Tu es Jarvis")

    assert result.text == "Bonjour, je suis Jarvis."
    assert result.model == "gpt-oss:120b"
    assert result.intent is IntentClass.CONVERSATIONAL
    assert result.input_tokens == 10
    assert result.output_tokens == 4
    assert result.estimated_prompt_tokens >= 1
    ollama.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_preserves_intent_in_result() -> None:
    ollama = _make_ollama_mock()
    router = LlmRouter(backend=ollama)

    for intent in [
        IntentClass.SIMPLE,
        IntentClass.COMPLEX,
        IntentClass.CODE,
        IntentClass.TOOL_USE,
    ]:
        result = await router.execute("test", intent)
        assert result.intent is intent


@pytest.mark.asyncio
async def test_execute_passes_max_tokens_and_system_through() -> None:
    ollama = _make_ollama_mock()
    router = LlmRouter(backend=ollama)

    await router.execute(
        "longer prompt",
        IntentClass.CODE,
        max_tokens=256,
        system="Be concise",
    )

    ollama.complete.assert_awaited_once_with(
        "longer prompt",
        max_tokens=256,
        system="Be concise",
    )
