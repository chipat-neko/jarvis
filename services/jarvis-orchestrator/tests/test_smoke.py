"""Tests smoke pour jarvis-orchestrator.

Permettent au CI de collecter au moins un test (pytest exit 5 = no tests collected,
ce qui ferait planter le workflow). À remplir vraiment au sprint S2+.
"""

from __future__ import annotations


def test_orchestrator_package_importable() -> None:
    """Le package orchestrator doit être importable."""
    import orchestrator  # noqa: F401


def test_proto_gen_modules_importable() -> None:
    """Les modules proto_gen générés doivent être importables."""
    from orchestrator.proto_gen import (  # noqa: F401
        common_pb2,
        voice_pb2,
        voice_pb2_grpc,
    )


def test_voice_client_module_importable() -> None:
    """Le client gRPC voice doit être importable."""
    from orchestrator.clients import voice_client

    assert voice_client.DEFAULT_VOICE_ADDRESS == "127.0.0.1:50051"


def test_llm_client_module_importable() -> None:
    """Le client gRPC llm doit être importable."""
    from orchestrator.clients import llm_client

    assert llm_client.DEFAULT_LLM_ADDRESS == "127.0.0.1:50052"


def test_chat_module_importable() -> None:
    """Le REPL de chat doit être importable (sans le lancer)."""
    from orchestrator import chat

    assert "Jarvis" in chat.DEFAULT_SYSTEM_PROMPT
