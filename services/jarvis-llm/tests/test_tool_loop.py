"""Tests de la boucle tool calling (mock backend)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from jarvis_llm.clients.ollama_client import OllamaCompletion, OllamaToolCall
from jarvis_llm.tool_loop import descriptors_to_ollama_tools, run_tool_loop


def _completion(text: str = "", tool_calls=()) -> OllamaCompletion:
    return OllamaCompletion(
        text=text,
        model="fake",
        prompt_tokens=0,
        completion_tokens=0,
        tool_calls=tuple(tool_calls),
    )


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.model = "fake"
    return client


@pytest.mark.asyncio
async def test_no_tool_calls_returns_immediately(mock_client) -> None:
    mock_client.chat.return_value = _completion(text="bonjour Noah")
    res = await run_tool_loop(
        mock_client,
        [{"role": "user", "content": "salut"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
        tool_executor=lambda n, a: "unused",
    )
    assert res.final_text == "bonjour Noah"
    assert res.iterations == 1
    assert res.steps == ()
    assert res.hit_max_iterations is False
    assert mock_client.chat.call_count == 1


@pytest.mark.asyncio
async def test_single_tool_call_then_final(mock_client) -> None:
    mock_client.chat.side_effect = [
        _completion(
            tool_calls=[OllamaToolCall(name="echo", arguments={"text": "hi"})],
        ),
        _completion(text="résultat: hi"),
    ]
    executed: list[tuple[str, dict]] = []

    def executor(name: str, args: dict) -> str:
        executed.append((name, args))
        return args.get("text", "")

    res = await run_tool_loop(
        mock_client,
        [{"role": "user", "content": "echo hi"}],
        tools=[{"type": "function", "function": {"name": "echo"}}],
        tool_executor=executor,
    )
    assert res.iterations == 2
    assert res.final_text == "résultat: hi"
    assert executed == [("echo", {"text": "hi"})]
    assert len(res.steps) == 1
    assert res.steps[0].tool_results == ("hi",)


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_one_step(mock_client) -> None:
    mock_client.chat.side_effect = [
        _completion(
            tool_calls=[
                OllamaToolCall(name="a", arguments={}),
                OllamaToolCall(name="b", arguments={}),
            ],
        ),
        _completion(text="done"),
    ]

    res = await run_tool_loop(
        mock_client,
        [{"role": "user", "content": "do both"}],
        tools=[],
        tool_executor=lambda n, a: f"res-{n}",
    )
    assert res.iterations == 2
    assert res.steps[0].tool_results == ("res-a", "res-b")


@pytest.mark.asyncio
async def test_executor_exception_becomes_tool_error(mock_client) -> None:
    mock_client.chat.side_effect = [
        _completion(tool_calls=[OllamaToolCall(name="boom", arguments={})]),
        _completion(text="ok"),
    ]

    def executor(name: str, args: dict) -> str:
        raise RuntimeError("kaboom")

    res = await run_tool_loop(
        mock_client,
        [{"role": "user", "content": "x"}],
        tools=[],
        tool_executor=executor,
    )
    assert "[tool-error]" in res.steps[0].tool_results[0]
    assert "kaboom" in res.steps[0].tool_results[0]


@pytest.mark.asyncio
async def test_max_iterations_hit(mock_client) -> None:
    # Le modèle redemande toujours un tool call → on coupe après max_iterations
    mock_client.chat.side_effect = [
        _completion(tool_calls=[OllamaToolCall(name="loop", arguments={})]),
        _completion(tool_calls=[OllamaToolCall(name="loop", arguments={})]),
        _completion(tool_calls=[OllamaToolCall(name="loop", arguments={})]),
        _completion(text="forced final without tools"),
    ]

    res = await run_tool_loop(
        mock_client,
        [{"role": "user", "content": "go"}],
        tools=[],
        tool_executor=lambda n, a: "ok",
        max_iterations=3,
    )
    assert res.hit_max_iterations is True
    assert res.iterations == 3
    # Une iter finale sans tools en plus
    assert mock_client.chat.call_count == 4
    assert res.final_text == "forced final without tools"


# ---------------------------------------------------------------------------
# descriptors_to_ollama_tools
# ---------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str, description: str = "", input_schema: dict | None = None) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}


class _FakeDescriptor:
    def __init__(self, server: str, tool: _FakeTool) -> None:
        self.server = server
        self.tool = tool

    @property
    def qualified_name(self) -> str:
        return f"{self.server}.{self.tool.name}"


def test_descriptors_to_ollama_tools_replaces_dots() -> None:
    descriptors = [_FakeDescriptor("fs", _FakeTool("read_file", "lit un fichier"))]
    out = descriptors_to_ollama_tools(descriptors)
    assert len(out) == 1
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "fs_read_file"
    assert out[0]["function"]["description"] == "lit un fichier"
    assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}


def test_descriptors_to_ollama_tools_preserves_schema() -> None:
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    descriptors = [_FakeDescriptor("fs", _FakeTool("read_file", input_schema=schema))]
    out = descriptors_to_ollama_tools(descriptors)
    assert out[0]["function"]["parameters"] == schema
