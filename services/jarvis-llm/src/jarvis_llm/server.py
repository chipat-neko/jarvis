"""Serveur gRPC pour jarvis-llm.

Implémente Ping + Complete (non-streaming). Stream/RouteIntent arriveront plus tard.

Lancement local :
    python -m jarvis_llm.server [--no-cloud] [--no-local] [--address 127.0.0.1:50052]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from concurrent import futures

import grpc
from loguru import logger

from jarvis_llm import __version__
from jarvis_llm.clients.anthropic_client import AnthropicClient
from jarvis_llm.clients.ollama_client import OllamaClient
from jarvis_llm.proto_gen import common_pb2, llm_pb2, llm_pb2_grpc
from jarvis_llm.router import IntentClass, LlmRouter, RouteTarget
from jarvis_llm.secrets import get_anthropic_api_key

DEFAULT_LLM_ADDRESS = "127.0.0.1:50052"
GRACEFUL_SHUTDOWN_SECONDS = 5

_PROTO_INTENT_TO_ENUM = {
    llm_pb2.INTENT_UNSPECIFIED: IntentClass.CONVERSATIONAL,
    llm_pb2.INTENT_SIMPLE: IntentClass.SIMPLE,
    llm_pb2.INTENT_CONVERSATIONAL: IntentClass.CONVERSATIONAL,
    llm_pb2.INTENT_COMPLEX: IntentClass.COMPLEX,
    llm_pb2.INTENT_CODE: IntentClass.CODE,
    llm_pb2.INTENT_TOOL_USE: IntentClass.TOOL_USE,
}

_ROUTE_TARGET_TO_PROTO = {
    RouteTarget.LOCAL: llm_pb2.TARGET_LOCAL,
    RouteTarget.CLOUD: llm_pb2.TARGET_CLOUD,
}


def build_router(*, enable_cloud: bool = True, enable_local: bool = True) -> LlmRouter:
    """Construit un LlmRouter avec les clients disponibles selon l'environnement."""
    anthropic_client: AnthropicClient | None = None
    ollama_client: OllamaClient | None = None

    if enable_cloud:
        api_key = get_anthropic_api_key()
        if api_key:
            anthropic_client = AnthropicClient(api_key=api_key)
            logger.info("Anthropic client OK (clé trouvée)")
        else:
            logger.warning("ANTHROPIC_API_KEY introuvable (keyring + env vide). Pas de cloud.")

    if enable_local:
        # Ollama est instancié sans vérifier la connectivité (lazy). Si le serveur
        # local n'est pas up, l'appel échouera à `complete()` — le router fallback cloud.
        ollama_client = OllamaClient()
        logger.info("Ollama client OK (host={})", ollama_client.host)

    return LlmRouter(anthropic_client=anthropic_client, ollama_client=ollama_client)


class LlmServicer(llm_pb2_grpc.LlmServiceServicer):
    """Implémentation du service gRPC LlmService."""

    def __init__(self, router: LlmRouter) -> None:
        self._router = router

    def Ping(
        self,
        request: llm_pb2.PingRequest,
        context: grpc.ServicerContext,
    ) -> llm_pb2.PingResponse:
        logger.info("Ping reçu de client_id={}", request.client_id)
        status = common_pb2.Status(
            code=common_pb2.Status.Code.OK,
            message=f"pong from jarvis-llm (client={request.client_id})",
        )
        return llm_pb2.PingResponse(status=status, version=__version__)

    def Complete(
        self,
        request: llm_pb2.CompleteRequest,
        context: grpc.ServicerContext,
    ) -> llm_pb2.CompleteResponse:
        logger.info(
            "Complete reçu de client_id={} (intent={}, prompt={} chars)",
            request.client_id,
            request.intent,
            len(request.prompt),
        )

        intent = _PROTO_INTENT_TO_ENUM.get(request.intent, IntentClass.CONVERSATIONAL)
        max_tokens = request.max_tokens if request.max_tokens > 0 else 1024
        system = request.system_prompt or None

        try:
            result = asyncio.run(
                self._router.execute(
                    request.prompt,
                    intent,
                    max_tokens=max_tokens,
                    system=system,
                )
            )
        except Exception as exc:
            logger.exception("Complete a échoué : {}", exc)
            error_status = common_pb2.Status(
                code=common_pb2.Status.Code.ERROR,
                message=f"{type(exc).__name__}: {exc}",
            )
            return llm_pb2.CompleteResponse(status=error_status)

        ok_status = common_pb2.Status(
            code=common_pb2.Status.Code.OK,
            message=result.reason,
        )
        return llm_pb2.CompleteResponse(
            status=ok_status,
            text=result.text,
            target=_ROUTE_TARGET_TO_PROTO[result.target],
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            reason=result.reason,
        )


def serve(
    address: str = DEFAULT_LLM_ADDRESS,
    *,
    enable_cloud: bool = True,
    enable_local: bool = True,
) -> None:
    """Démarre le serveur gRPC et bloque jusqu'à interruption."""
    router = build_router(enable_cloud=enable_cloud, enable_local=enable_local)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    llm_pb2_grpc.add_LlmServiceServicer_to_server(LlmServicer(router), server)
    server.add_insecure_port(address)
    server.start()
    logger.info("jarvis-llm listening on {} (version {})", address, __version__)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("SIGINT reçu — arrêt gracieux ({}s max)", GRACEFUL_SHUTDOWN_SECONDS)
        server.stop(GRACEFUL_SHUTDOWN_SECONDS).wait()


def main() -> int:
    """Entry point CLI : `python -m jarvis_llm.server` ou `jarvis-llm`."""
    parser = argparse.ArgumentParser(description="Serveur gRPC jarvis-llm")
    parser.add_argument("--address", default=DEFAULT_LLM_ADDRESS, help="host:port d'écoute")
    parser.add_argument("--no-cloud", action="store_true", help="désactive Anthropic")
    parser.add_argument("--no-local", action="store_true", help="désactive Ollama")
    args = parser.parse_args()

    try:
        serve(
            args.address,
            enable_cloud=not args.no_cloud,
            enable_local=not args.no_local,
        )
    except Exception as exc:
        logger.exception("Erreur fatale : {}", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
