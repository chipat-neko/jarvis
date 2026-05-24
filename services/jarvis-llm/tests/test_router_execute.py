"""Tests du dispatching LlmRouter.execute() avec clients mockés.

Ces tests ne touchent ni Ollama ni l'API Anthropic — ils valident uniquement
la logique de fallback et le mapping vers CompletionResult.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from jarvis_llm.clients.anthropic_client import AnthropicCompletion
from jarvis_llm.clients.ollama_client import OllamaCompletion
from jarvis_llm.router import IntentClass, LlmRouter, RouteTarget


def _make_anthropic_mock(text: str = "cloud-reply") -> AsyncMock:
    mock = AsyncMock()
    mock.complete = AsyncMock(
        return_value=AnthropicCompletion(
            text=text,
            model="claude-sonnet-4-6",
            input_tokens=42,
            output_tokens=7,
        )
    )
    return mock


def _make_ollama_mock(text: str = "local-reply") -> AsyncMock:
    mock = AsyncMock()
    mock.complete = AsyncMock(
        return_value=OllamaCompletion(
            text=text,
            model="qwen2.5:14b-instruct-q4_K_M",
            prompt_tokens=10,
            completion_tokens=4,
        )
    )
    return mock


@pytest.mark.asyncio
async def test_execute_simple_intent_uses_local_client() -> None:
    anthropic = _make_anthropic_mock()
    ollama = _make_ollama_mock("salut, c'est qwen")
    router = LlmRouter(anthropic_client=anthropic, ollama_client=ollama)

    result = await router.execute("Quelle heure ?", IntentClass.SIMPLE)

    assert result.target is RouteTarget.LOCAL
    assert result.text == "salut, c'est qwen"
    ollama.complete.assert_awaited_once()
    anthropic.complete.assert_not_called()


@pytest.mark.asyncio
async def test_execute_code_intent_uses_cloud_client() -> None:
    anthropic = _make_anthropic_mock("here is your refactor")
    ollama = _make_ollama_mock()
    router = LlmRouter(anthropic_client=anthropic, ollama_client=ollama)

    result = await router.execute("Refactor ce code", IntentClass.CODE)

    assert result.target is RouteTarget.CLOUD
    assert result.text == "here is your refactor"
    anthropic.complete.assert_awaited_once()
    ollama.complete.assert_not_called()


@pytest.mark.asyncio
async def test_execute_falls_back_to_cloud_when_local_missing() -> None:
    anthropic = _make_anthropic_mock("fallback cloud reply")
    router = LlmRouter(anthropic_client=anthropic, ollama_client=None)

    result = await router.execute("Coucou", IntentClass.CONVERSATIONAL)

    assert result.target is RouteTarget.CLOUD
    assert "fallback" in result.reason.lower()
    anthropic.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_falls_back_to_local_when_cloud_missing() -> None:
    ollama = _make_ollama_mock("fallback local")
    router = LlmRouter(anthropic_client=None, ollama_client=ollama)

    # intent CODE veut normalement aller cloud → bascule local car pas de cloud
    result = await router.execute("Refactor X", IntentClass.CODE)

    assert result.target is RouteTarget.LOCAL
    assert "fallback" in result.reason.lower()
    ollama.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_raises_without_any_client() -> None:
    router = LlmRouter(anthropic_client=None, ollama_client=None)

    with pytest.raises(RuntimeError, match="Aucun client LLM"):
        await router.execute("Salut", IntentClass.CONVERSATIONAL)
