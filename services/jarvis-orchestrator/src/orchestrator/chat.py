"""CLI conversationnelle Jarvis (MVP texte).

REPL minimal :
    > tu tapes un message
    Jarvis: réponse du LLM (Sonnet 4.6 par défaut, Qwen 14B si intent simple + Ollama dispo)

Modes :
- in-process (par défaut) : appel direct du router LlmRouter dans le même process.
  Pas besoin de démarrer jarvis-llm séparément. Idéal pour Noah qui veut juste
  essayer.
- gRPC (--via-grpc) : passe par le service jarvis-llm distant (port 50052).
  Plus proche de l'archi cible mais nécessite de lancer le server avant.

Usage :
    py -3.11 -m orchestrator.chat                   # mode in-process
    py -3.11 -m orchestrator.chat --no-cloud        # force le local Ollama uniquement
    py -3.11 -m orchestrator.chat --via-grpc        # passe par jarvis-llm gRPC

Commandes spéciales pendant le REPL :
    /quit, /exit, Ctrl+C    -> sortir
    /reset                  -> oublier l'historique
    /target                 -> afficher la dernière cible de routing
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from jarvis_llm.clients.anthropic_client import AnthropicClient
from jarvis_llm.clients.ollama_client import OllamaClient
from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import LlmRouter
from jarvis_llm.secrets import get_anthropic_api_key
from orchestrator.clients import llm_client as grpc_llm_client

DEFAULT_SYSTEM_PROMPT = (
    "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
    "français (sauf si l'utilisateur écrit en anglais), sans phrases creuses, "
    "et tu vas droit au but. Tu peux refuser poliment ce que tu ne sais pas faire."
)


# ---------------------------------------------------------------------------
# Mode in-process : on construit un LlmRouter local et on l'appelle directement.
# ---------------------------------------------------------------------------


def _build_in_process_router(*, enable_cloud: bool, enable_local: bool) -> LlmRouter:
    anthropic_client: AnthropicClient | None = None
    ollama_client: OllamaClient | None = None

    if enable_cloud:
        api_key = get_anthropic_api_key()
        if api_key:
            anthropic_client = AnthropicClient(api_key=api_key)
        else:
            print(
                "⚠️  Aucune clé Anthropic trouvée (keyring + env). Mode local-only.",
                file=sys.stderr,
            )

    if enable_local:
        ollama_client = OllamaClient()

    if anthropic_client is None and ollama_client is None:
        raise RuntimeError(
            "Aucun backend LLM disponible. Configure ANTHROPIC_API_KEY ou installe Ollama."
        )

    return LlmRouter(anthropic_client=anthropic_client, ollama_client=ollama_client)


async def _answer_in_process(router: LlmRouter, prompt: str) -> tuple[str, str, str]:
    intent = classify(prompt)
    result = await router.execute(
        prompt,
        intent,
        system=DEFAULT_SYSTEM_PROMPT,
    )
    return result.text, result.target.value, result.reason


# ---------------------------------------------------------------------------
# Mode gRPC : on délègue à jarvis-llm via le client orchestrator.
# ---------------------------------------------------------------------------


def _answer_via_grpc(prompt: str, address: str) -> tuple[str, str, str]:
    intent = classify(prompt).value  # "code", "simple", ...
    result = grpc_llm_client.complete(
        prompt=prompt,
        intent=intent,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        address=address,
        client_id="orchestrator-chat",
    )
    if not result.ok:
        raise RuntimeError(f"jarvis-llm a renvoyé une erreur : {result.status_message}")
    return result.text, result.target, result.reason


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def _print_banner(*, via_grpc: bool, cloud_ok: bool, local_ok: bool) -> None:
    mode = "gRPC (jarvis-llm)" if via_grpc else "in-process"
    backends = []
    if cloud_ok:
        backends.append("cloud Sonnet 4.6")
    if local_ok:
        backends.append("local Qwen 14B")
    print("┌─────────────────────────────────────────────────────────┐")
    print("│  Jarvis MVP — chat texte                                │")
    print(f"│  mode     : {mode:<43}│")
    print(f"│  backends : {', '.join(backends) or 'aucun (!)':<43}│")
    print("│  /quit pour sortir, /reset pour effacer l'historique    │")
    print("└─────────────────────────────────────────────────────────┘")


def run_repl(
    *,
    via_grpc: bool,
    enable_cloud: bool,
    enable_local: bool,
    grpc_address: str,
) -> int:
    router: LlmRouter | None = None
    cloud_ok = enable_cloud and (get_anthropic_api_key() is not None)
    local_ok = enable_local

    if not via_grpc:
        router = _build_in_process_router(enable_cloud=enable_cloud, enable_local=enable_local)

    _print_banner(via_grpc=via_grpc, cloud_ok=cloud_ok or via_grpc, local_ok=local_ok or via_grpc)

    last_target = "?"

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

        if user.lower() == "/target":
            print(f"Dernière cible : {last_target}")
            continue

        try:
            if via_grpc:
                text, target, reason = _answer_via_grpc(user, address=grpc_address)
            else:
                assert router is not None
                text, target, reason = asyncio.run(_answer_in_process(router, user))
        except Exception as exc:
            print(f"❌ Erreur : {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        last_target = target
        print(f"\nJarvis [{target}]> {text}")
        print(f"  ↳ {reason}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="REPL de chat Jarvis (MVP texte cloud + local)",
    )
    parser.add_argument(
        "--via-grpc",
        action="store_true",
        help="passe par le service jarvis-llm distant (gRPC) au lieu d'appeler en in-process",
    )
    parser.add_argument(
        "--no-cloud",
        action="store_true",
        help="désactive Anthropic (force local Ollama)",
    )
    parser.add_argument(
        "--no-local",
        action="store_true",
        help="désactive Ollama (force cloud Anthropic)",
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
            enable_cloud=not args.no_cloud,
            enable_local=not args.no_local,
            grpc_address=args.grpc_address,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
