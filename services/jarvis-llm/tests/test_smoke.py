"""Tests smoke pour jarvis-llm (100% local via Ollama)."""

from __future__ import annotations


def test_package_importable() -> None:
    import jarvis_llm

    assert jarvis_llm.__version__ == "0.2.0"


def test_proto_gen_modules_importable() -> None:
    from jarvis_llm.proto_gen import (  # noqa: F401
        common_pb2,
        llm_pb2,
        llm_pb2_grpc,
    )


def test_ollama_client_importable() -> None:
    from jarvis_llm.clients.ollama_client import OllamaClient

    ollama = OllamaClient()
    assert ollama.host.startswith("http://")
    # Modèle par défaut peut être override via env, on vérifie juste qu'il y a une valeur
    assert ollama.model


def test_router_rejects_none_backend() -> None:
    import pytest

    from jarvis_llm.router import LlmRouter

    with pytest.raises(ValueError, match="backend requis"):
        LlmRouter(backend=None)  # type: ignore[arg-type]


def test_huggingface_client_importable() -> None:
    from jarvis_llm.clients.huggingface_client import HuggingFaceClient

    # Pas de chargement (lazy) — on vérifie juste l'attribut.
    client = HuggingFaceClient(model_id="Qwen/Qwen2.5-Coder-3B-Instruct")
    assert client.model == "Qwen/Qwen2.5-Coder-3B-Instruct"
    assert client.quantize_4bit is False


def test_server_module_importable() -> None:
    from jarvis_llm import server

    assert server.DEFAULT_LLM_ADDRESS == "127.0.0.1:50052"
