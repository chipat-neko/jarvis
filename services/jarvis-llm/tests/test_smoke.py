"""Tests smoke pour jarvis-llm.

Vérifient l'importabilité des modules + la cohérence des décisions de routing
sur quelques cas évidents. Les vrais tests d'intégration (Ollama, Anthropic)
arrivent au sprint S2 quand les clients seront branchés.
"""

from __future__ import annotations


def test_package_importable() -> None:
    import jarvis_llm

    assert jarvis_llm.__version__ == "0.1.0"


def test_proto_gen_modules_importable() -> None:
    from jarvis_llm.proto_gen import (  # noqa: F401
        common_pb2,
        llm_pb2,
        llm_pb2_grpc,
    )


def test_clients_importable() -> None:
    from jarvis_llm.clients.anthropic_client import AnthropicClient
    from jarvis_llm.clients.ollama_client import OllamaClient

    ollama = OllamaClient()
    assert ollama.host == "http://127.0.0.1:11434"
    assert ollama.model.startswith("qwen2.5")

    # AnthropicClient exige une clé API non-vide
    client = AnthropicClient(api_key="sk-ant-test-dummy")
    assert client.model == "claude-sonnet-4-6"


def test_anthropic_client_rejects_empty_key() -> None:
    import pytest

    from jarvis_llm.clients.anthropic_client import AnthropicClient

    with pytest.raises(ValueError, match="api_key requis"):
        AnthropicClient(api_key="")


def test_router_simple_intent_goes_local() -> None:
    from jarvis_llm.router import IntentClass, LlmRouter, RouteTarget

    router = LlmRouter()
    decision = router.decide("Quelle heure est-il ?", IntentClass.SIMPLE)

    assert decision.target == RouteTarget.LOCAL
    assert decision.estimated_tokens >= 1


def test_router_code_intent_goes_cloud() -> None:
    from jarvis_llm.router import IntentClass, LlmRouter, RouteTarget

    router = LlmRouter()
    decision = router.decide("Refactor ce code Python", IntentClass.CODE)

    assert decision.target == RouteTarget.CLOUD


def test_router_long_prompt_goes_cloud() -> None:
    from jarvis_llm.router import IntentClass, LlmRouter, RouteTarget

    router = LlmRouter()
    long_prompt = "x" * (4 * 3000)  # ~3000 tokens estimés (>2000 seuil)
    decision = router.decide(long_prompt, IntentClass.CONVERSATIONAL)

    assert decision.target == RouteTarget.CLOUD
    assert decision.estimated_tokens > 2000


def test_server_module_importable() -> None:
    from jarvis_llm import server

    assert server.DEFAULT_LLM_ADDRESS == "127.0.0.1:50052"
