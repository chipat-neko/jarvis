"""Tests des wrappers Anthropic/Ollama avec mocks (pas d'appel réseau)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from jarvis_llm.clients.anthropic_client import AnthropicClient, _extract_text
from jarvis_llm.clients.ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_anthropic_complete_maps_response() -> None:
    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hello "),
            SimpleNamespace(type="text", text="world."),
            SimpleNamespace(type="tool_use", text="(ignored)"),
        ],
        model="claude-sonnet-4-6",
        usage=SimpleNamespace(
            input_tokens=12,
            output_tokens=5,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )

    with patch("anthropic.AsyncAnthropic") as mock_class:
        mock_class.return_value.messages.create = AsyncMock(return_value=fake_response)
        client = AnthropicClient(api_key="sk-ant-test")
        result = await client.complete("Hi", max_tokens=10, system="Be brief")

    assert result.text == "Hello world."
    assert result.model == "claude-sonnet-4-6"
    assert result.input_tokens == 12
    assert result.output_tokens == 5


def test_extract_text_ignores_non_text_blocks() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", text="x"),
            SimpleNamespace(type="text", text="real-content"),
        ],
    )
    assert _extract_text(response) == "real-content"


@pytest.mark.asyncio
async def test_ollama_complete_maps_chat_response() -> None:
    fake_response = {
        "message": {"content": "salut, ça va !"},
        "model": "qwen2.5:14b-instruct-q4_K_M",
        "prompt_eval_count": 8,
        "eval_count": 5,
    }

    with patch("ollama.AsyncClient") as mock_class:
        mock_class.return_value.chat = AsyncMock(return_value=fake_response)
        client = OllamaClient()
        result = await client.complete("Salut", system="Tu es Jarvis")

    assert result.text == "salut, ça va !"
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 5
    assert result.model == "qwen2.5:14b-instruct-q4_K_M"
