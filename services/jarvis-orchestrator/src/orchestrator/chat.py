"""CLI conversationnelle Jarvis (MVP texte, 100% local).

REPL minimal :
    > tu tapes un message
    Jarvis: réponse du LLM local (Ollama gpt-oss:120b par défaut, ou HF transformers)

Modes :
- in-process (par défaut) : appel direct du router dans le même process. Pas
  besoin de démarrer jarvis-llm séparément. Idéal pour test rapide.
- gRPC (--via-grpc) : passe par le service jarvis-llm distant (port 50052).

Backends :
- ollama (défaut) : Ollama HTTP local, modèle gpt-oss:120b par défaut
- hf : transformers in-process, modèle Qwen/Qwen2.5-Coder-7B-Instruct par défaut
  (utilise les modèles HF déjà téléchargés dans HF_HOME / D:\\.cache\\huggingface)

Usage :
    py -3.11 -m orchestrator.chat                                   # ollama gpt-oss:120b
    py -3.11 -m orchestrator.chat --ollama-model qwen2.5:14b-instruct-q4_K_M
    py -3.11 -m orchestrator.chat --backend hf                      # HF Qwen2.5-Coder-7B-Instruct
    py -3.11 -m orchestrator.chat --backend hf --hf-model microsoft/phi-2
    py -3.11 -m orchestrator.chat --backend hf --quantize-4bit      # 4-bit quantization
    py -3.11 -m orchestrator.chat --via-grpc                        # via jarvis-llm:50052

Commandes spéciales :
    /quit, /exit, Ctrl+C    -> sortir
    /reset                  -> oublier l'historique (non implémenté dans ce MVP)
    /model                  -> afficher le modèle utilisé
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from jarvis_llm.clients.huggingface_client import DEFAULT_HF_MODEL, HuggingFaceClient
from jarvis_llm.clients.ollama_client import DEFAULT_LOCAL_MODEL, OllamaClient
from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import LlmBackend, LlmRouter
from orchestrator.clients import llm_client as grpc_llm_client

DEFAULT_BACKEND = "ollama"
DEFAULT_SYSTEM_PROMPT = (
    "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
    "français (sauf si l'utilisateur écrit en anglais), sans phrases creuses, "
    "et tu vas droit au but. Tu peux refuser poliment ce que tu ne sais pas faire."
)


def _build_in_process_router(
    *,
    backend: str,
    ollama_model: str,
    hf_model: str,
    quantize_4bit: bool,
) -> LlmRouter:
    chosen: LlmBackend
    if backend == "ollama":
        chosen = OllamaClient(model=ollama_model)
    elif backend == "hf":
        chosen = HuggingFaceClient(model_id=hf_model, quantize_4bit=quantize_4bit)
    else:
        raise ValueError(f"backend invalide '{backend}'. Choix: ollama, hf")
    return LlmRouter(backend=chosen)


async def _answer_in_process(router: LlmRouter, prompt: str) -> tuple[str, str, str]:
    intent = classify(prompt)
    result = await router.execute(prompt, intent, system=DEFAULT_SYSTEM_PROMPT)
    return result.text, result.model, result.intent.value


def _answer_via_grpc(prompt: str, address: str) -> tuple[str, str, str]:
    intent = classify(prompt).value
    result = grpc_llm_client.complete(
        prompt=prompt,
        intent=intent,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        address=address,
        client_id="orchestrator-chat",
    )
    if not result.ok:
        raise RuntimeError(f"jarvis-llm a renvoyé une erreur : {result.status_message}")
    return result.text, result.model, result.intent


def _print_banner(*, via_grpc: bool, backend: str, model: str) -> None:
    mode = "gRPC (jarvis-llm)" if via_grpc else "in-process"
    print("┌─────────────────────────────────────────────────────────┐")
    print("│  Jarvis MVP — chat texte (100% local)                   │")
    print(f"│  mode    : {mode:<44}│")
    print(f"│  backend : {backend:<44}│")
    print(f"│  model   : {model:<44}│")
    print("│  /quit pour sortir, /model pour voir le modèle          │")
    print("└─────────────────────────────────────────────────────────┘")


def run_repl(
    *,
    via_grpc: bool,
    backend: str,
    ollama_model: str,
    hf_model: str,
    quantize_4bit: bool,
    grpc_address: str,
) -> int:
    router: LlmRouter | None = None
    if not via_grpc:
        router = _build_in_process_router(
            backend=backend,
            ollama_model=ollama_model,
            hf_model=hf_model,
            quantize_4bit=quantize_4bit,
        )

    display_model = ollama_model if backend == "ollama" else hf_model
    _print_banner(via_grpc=via_grpc, backend=backend, model=display_model)
    if backend == "hf" and not via_grpc:
        print("(1er appel HF : chargement modèle, peut prendre 30s à 2min…)", file=sys.stderr)

    last_model = display_model

    while True:
        try:
            user = input("\nVous> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye.")
            return 0

        if not user:
            continue

        if user.lower() in {"/quit", "/exit", "exit", "quit"}:
            print("👋 Bye.")
            return 0

        if user.lower() == "/reset":
            print("(historique non implémenté dans ce MVP — chaque tour est indépendant)")
            continue

        if user.lower() == "/model":
            print(f"Dernier modèle : {last_model}")
            continue

        try:
            if via_grpc:
                text, used_model, intent = _answer_via_grpc(user, address=grpc_address)
            else:
                assert router is not None
                text, used_model, intent = asyncio.run(_answer_in_process(router, user))
        except Exception as exc:
            print(f"❌ Erreur : {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        last_model = used_model
        print(f"\nJarvis> {text}")
        print(f"  ↳ model={used_model} intent={intent}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="REPL de chat Jarvis (MVP texte, 100% local : Ollama ou HuggingFace)",
    )
    parser.add_argument(
        "--via-grpc",
        action="store_true",
        help="passe par le service jarvis-llm distant (gRPC)",
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "hf"],
        default=DEFAULT_BACKEND,
        help="backend LLM : ollama (HTTP) ou hf (transformers in-process)",
    )
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_LOCAL_MODEL,
        help=f"modèle Ollama si --backend ollama (défaut {DEFAULT_LOCAL_MODEL})",
    )
    parser.add_argument(
        "--hf-model",
        default=DEFAULT_HF_MODEL,
        help=f"modèle HF si --backend hf (défaut {DEFAULT_HF_MODEL})",
    )
    parser.add_argument(
        "--quantize-4bit",
        action="store_true",
        help="quantization 4-bit pour --backend hf (utile sur gros modèles)",
    )
    parser.add_argument(
        "--grpc-address",
        default=grpc_llm_client.DEFAULT_LLM_ADDRESS,
        help="adresse jarvis-llm en mode --via-grpc",
    )
    args = parser.parse_args()

    try:
        return run_repl(
            via_grpc=args.via_grpc,
            backend=args.backend,
            ollama_model=args.ollama_model,
            hf_model=args.hf_model,
            quantize_4bit=args.quantize_4bit,
            grpc_address=args.grpc_address,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
