"""Serveur gRPC pour jarvis-llm.

Implémente pour l'instant uniquement le RPC `Ping` défini dans proto/llm.proto.
Les RPC Complete / Stream / RouteIntent arriveront au sprint S2.

Lancement local :
    python -m jarvis_llm.server
"""

from __future__ import annotations

import sys
from concurrent import futures

import grpc
from loguru import logger

from jarvis_llm import __version__
from jarvis_llm.proto_gen import common_pb2, llm_pb2, llm_pb2_grpc

DEFAULT_LLM_ADDRESS = "127.0.0.1:50052"
GRACEFUL_SHUTDOWN_SECONDS = 5


class LlmServicer(llm_pb2_grpc.LlmServiceServicer):
    """Implémentation du service gRPC LlmService."""

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


def serve(address: str = DEFAULT_LLM_ADDRESS) -> None:
    """Démarre le serveur gRPC et bloque jusqu'à interruption."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    llm_pb2_grpc.add_LlmServiceServicer_to_server(LlmServicer(), server)
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
    try:
        serve()
    except Exception as exc:
        logger.exception("Erreur fatale : {}", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
