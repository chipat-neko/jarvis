"""CLI conversationnelle Jarvis (MVP texte, 100% local).

REPL minimal :
    > tu tapes un message
    Jarvis: réponse du LLM local (gpt-oss:120b par défaut, override via $JARVIS_LLM_MODEL)

Modes :
- in-process (par défaut) : appel direct du router LlmRouter dans le même process.
  Pas besoin de démarrer jarvis-llm séparément. Idéal pour test rapide.
- gRPC (--via-grpc) : passe par le service jarvis-llm distant (port 50052).
  Plus proche de l'archi cible mais nécessite de lancer le server avant.

Usage :
    py -3.11 -m orchestrator.chat                   # mode in-process
    py -3.11 -m orchestrator.chat --model qwen2.5:14b-instruct-q4_K_M
    py -3.11 -m orchestrator.chat --via-grpc

Commandes spéciales pendant le REPL :
    /quit, /exit, Ctrl+C    -> sortir
    /reset                  -> oublier l'historique (non implémenté dans ce MVP)
    /model                  -> afficher le modèle utilisé
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from jarvis_llm.clients.ollama_client import DEFAULT_LOCAL_MODEL, OllamaClient
from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import LlmRouter
from orchestrator.clients import llm_client as grpc_llm_client

DEFAULT_SYSTEM_PROMPT = (
    "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
    "français (sauf si l'utilisateur écrit en anglais), sans phrases creuses, "
    "et tu vas droit au but. Tu peux refuser poliment ce que tu ne sais pas faire."
)


def _build_in_process_router(*, model: str) -> LlmRouter:
    ollama_client = OllamaClient(model=model)
    return LlmRouter(ollama_client=ollama_client)


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


def _print_banner(*, via_grpc: bool, model: str) -> None:
    mode = "gRPC (jarvis-llm)" if via_grpc else "in-process"
    print("┌─────────────────────────────────────────────────────────┐")
    print("│  Jarvis MVP — chat texte (100% local)                   │")
    print(f"│  mode  : {mode:<46}│")
    print(f"│  model : {model:<46}│")
    print("│  /quit pour sortir, /model pour voir le modèle          │")
    print("└─────────────────────────────────────────────────────────┘")


def run_repl(*, via_grpc: bool, model: str, grpc_address: str) -> int:
    router: LlmRouter | None = None
    if not via_grpc:
        router = _build_in_process_router(model=model)

    _print_banner(via_grpc=via_grpc, model=model)

    last_model = model

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
        description="REPL de chat Jarvis (MVP texte, 100% local via Ollama)",
    )
    parser.add_argument(
        "--via-grpc",
        action="store_true",
        help="passe par le service jarvis-llm distant (gRPC) au lieu d'appeler en in-process",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_LOCAL_MODEL,
        help=f"modèle Ollama à utiliser (défaut {DEFAULT_LOCAL_MODEL}, override via $JARVIS_LLM_MODEL)",
    )
    parser.add_argument(
        "--grpc-address",
        default=grpc_llm_client.DEFAULT_LLM_ADDRESS,
        help="adresse jarvis-llm en mode --via-grpc",
    )
    args = parser.parse_args()

    try:
        return run_repl(via_grpc=args.via_grpc, model=args.model, grpc_address=args.grpc_address)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
