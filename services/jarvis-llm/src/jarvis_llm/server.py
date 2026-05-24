"""Serveur gRPC pour jarvis-llm (100% local via Ollama).

Implémente Ping + Complete (non-streaming). Streaming arrivera plus tard.

Lancement local :
    python -m jarvis_llm.server [--address 127.0.0.1:50052] [--model gpt-oss:120b]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from concurrent import futures

import grpc
from loguru import logger

from jarvis_llm import __version__
from jarvis_llm.clients.huggingface_client import DEFAULT_HF_MODEL, HuggingFaceClient
from jarvis_llm.clients.ollama_client import DEFAULT_LOCAL_MODEL, OllamaClient
from jarvis_llm.proto_gen import common_pb2, llm_pb2, llm_pb2_grpc
from jarvis_llm.router import IntentClass, LlmBackend, LlmRouter

DEFAULT_BACKEND = "ollama"  # "ollama" ou "hf"

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

_INTENT_TO_PROTO = {
    IntentClass.SIMPLE: llm_pb2.INTENT_SIMPLE,
    IntentClass.CONVERSATIONAL: llm_pb2.INTENT_CONVERSATIONAL,
    IntentClass.COMPLEX: llm_pb2.INTENT_COMPLEX,
    IntentClass.CODE: llm_pb2.INTENT_CODE,
    IntentClass.TOOL_USE: llm_pb2.INTENT_TOOL_USE,
}


def build_router(
    *,
    backend: str = DEFAULT_BACKEND,
    ollama_model: str = DEFAULT_LOCAL_MODEL,
    hf_model: str = DEFAULT_HF_MODEL,
    quantize_4bit: bool = False,
) -> LlmRouter:
    """Construit un LlmRouter avec le backend choisi.

    Args:
        backend: "ollama" (HTTP local) ou "hf" (transformers in-process).
        ollama_model: nom du modèle Ollama si backend=ollama.
        hf_model: ID HF si backend=hf.
        quantize_4bit: 4-bit (bitsandbytes) si backend=hf (utile pour gros modèles).
    """
    chosen: LlmBackend
    if backend == "ollama":
        chosen = OllamaClient(model=ollama_model)
        logger.info("Backend Ollama (host={}, model={})", chosen.host, chosen.model)
    elif backend == "hf":
        chosen = HuggingFaceClient(model_id=hf_model, quantize_4bit=quantize_4bit)
        logger.info("Backend HuggingFace (model={}, 4bit={})", chosen.model, quantize_4bit)
    else:
        raise ValueError(f"backend invalide '{backend}'. Choix: ollama, hf")
    return LlmRouter(backend=chosen)


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
            message=f"intent={result.intent.value} model={result.model}",
        )
        return llm_pb2.CompleteResponse(
            status=ok_status,
            text=result.text,
            model=result.model,
            intent=_INTENT_TO_PROTO[result.intent],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_prompt_tokens=result.estimated_prompt_tokens,
        )


def serve(
    address: str = DEFAULT_LLM_ADDRESS,
    *,
    backend: str = DEFAULT_BACKEND,
    ollama_model: str = DEFAULT_LOCAL_MODEL,
    hf_model: str = DEFAULT_HF_MODEL,
    quantize_4bit: bool = False,
) -> None:
    """Démarre le serveur gRPC et bloque jusqu'à interruption."""
    router = build_router(
        backend=backend,
        ollama_model=ollama_model,
        hf_model=hf_model,
        quantize_4bit=quantize_4bit,
    )
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
    """Entry point CLI : `python -m jarvis_llm.server`."""
    parser = argparse.ArgumentParser(description="Serveur gRPC jarvis-llm (100% local)")
    parser.add_argument("--address", default=DEFAULT_LLM_ADDRESS, help="host:port d'écoute")
    parser.add_argument(
        "--backend",
        choices=["ollama", "hf"],
        default=DEFAULT_BACKEND,
        help="backend LLM : ollama (HTTP) ou hf (transformers in-process)",
    )
    parser.add_argument(
        "--ollama-model", default=DEFAULT_LOCAL_MODEL, help="modèle Ollama si --backend ollama"
    )
    parser.add_argument("--hf-model", default=DEFAULT_HF_MODEL, help="modèle HF si --backend hf")
    parser.add_argument(
        "--quantize-4bit",
        action="store_true",
        help="quantization 4-bit (bitsandbytes) pour --backend hf (utile pour gros modèles)",
    )
    args = parser.parse_args()

    try:
        serve(
            args.address,
            backend=args.backend,
            ollama_model=args.ollama_model,
            hf_model=args.hf_model,
            quantize_4bit=args.quantize_4bit,
        )
    except Exception as exc:
        logger.exception("Erreur fatale : {}", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
