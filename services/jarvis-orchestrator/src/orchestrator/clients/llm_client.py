"""Client gRPC pour communiquer avec jarvis-llm (100% local).

Usage rapide :

    from orchestrator.clients.llm_client import complete, ping_llm
    resp = complete(prompt="Bonjour")
    print(resp.text)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import grpc

from orchestrator.proto_gen import llm_pb2, llm_pb2_grpc

DEFAULT_LLM_ADDRESS = "127.0.0.1:50052"
STATUS_CODE_OK = 1  # cf proto/common.proto Status.Code.OK


@dataclass
class LlmPingResult:
    ok: bool
    message: str
    version: str


@dataclass
class LlmCompleteResult:
    ok: bool
    text: str
    model: str
    intent: str  # "simple" / "conversational" / "complex" / "code" / "tool_use"
    input_tokens: int
    output_tokens: int
    estimated_prompt_tokens: int
    status_message: str


# Aligné avec l'enum jarvis_llm.router.IntentClass
_INTENT_STR_TO_PROTO = {
    "simple": llm_pb2.INTENT_SIMPLE,
    "conversational": llm_pb2.INTENT_CONVERSATIONAL,
    "complex": llm_pb2.INTENT_COMPLEX,
    "code": llm_pb2.INTENT_CODE,
    "tool_use": llm_pb2.INTENT_TOOL_USE,
}

_INTENT_PROTO_TO_STR = {
    llm_pb2.INTENT_UNSPECIFIED: "unspecified",
    llm_pb2.INTENT_SIMPLE: "simple",
    llm_pb2.INTENT_CONVERSATIONAL: "conversational",
    llm_pb2.INTENT_COMPLEX: "complex",
    llm_pb2.INTENT_CODE: "code",
    llm_pb2.INTENT_TOOL_USE: "tool_use",
}


def ping_llm(
    *,
    client_id: str = "orchestrator",
    address: str = DEFAULT_LLM_ADDRESS,
    timeout_s: float = 5.0,
) -> LlmPingResult:
    """Ping le service jarvis-llm."""
    with grpc.insecure_channel(address) as channel:
        stub = llm_pb2_grpc.LlmServiceStub(channel)
        response = stub.Ping(llm_pb2.PingRequest(client_id=client_id), timeout=timeout_s)
        return LlmPingResult(
            ok=response.status.code == STATUS_CODE_OK,
            message=response.status.message,
            version=response.version,
        )


def complete(
    *,
    prompt: str,
    intent: str = "conversational",
    max_tokens: int = 1024,
    system_prompt: str = "",
    client_id: str = "orchestrator",
    address: str = DEFAULT_LLM_ADDRESS,
    timeout_s: float = 300.0,  # 5 min — modèles 120B peuvent être lents
) -> LlmCompleteResult:
    """Appel Complete bloquant vers jarvis-llm.

    `intent` est une string parmi : simple / conversational / complex / code / tool_use.
    Tout autre valeur sera mappée à INTENT_UNSPECIFIED côté serveur (= CONVERSATIONAL).
    """
    intent_proto = _INTENT_STR_TO_PROTO.get(intent.lower(), llm_pb2.INTENT_UNSPECIFIED)
    request = llm_pb2.CompleteRequest(
        prompt=prompt,
        intent=intent_proto,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
        client_id=client_id,
    )

    with grpc.insecure_channel(address) as channel:
        stub = llm_pb2_grpc.LlmServiceStub(channel)
        response = stub.Complete(request, timeout=timeout_s)

    return LlmCompleteResult(
        ok=response.status.code == STATUS_CODE_OK,
        text=response.text,
        model=response.model,
        intent=_INTENT_PROTO_TO_STR.get(response.intent, "unspecified"),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_prompt_tokens=response.estimated_prompt_tokens,
        status_message=response.status.message,
    )


def main() -> int:
    """CLI rapide : ping le service llm pour tester la connexion."""
    try:
        result = ping_llm(client_id="cli-test")
    except grpc.RpcError as exc:
        print(f"❌ Erreur gRPC : {exc.code().name} — {exc.details()}", file=sys.stderr)
        print(f"   Vérifie que jarvis-llm tourne sur {DEFAULT_LLM_ADDRESS}", file=sys.stderr)
        print("   (py -3.11 -m jarvis_llm.server dans un autre terminal)", file=sys.stderr)
        return 2

    icon = "✅" if result.ok else "❌"
    print(f"{icon} Ping/Pong avec jarvis-llm :")
    print(f"   message  : {result.message}")
    print(f"   version  : {result.version}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
