"""CLI conversationnelle Jarvis (MVP texte, 100% local, multi-tour).

REPL multi-tour avec historique persistant : Jarvis se souvient des messages
précédents dans la même session ET entre redémarrages (historique sauvegardé
dans `.local/conversation.json` à la racine du repo, gitignored).

Modes :
- in-process (par défaut) : appel direct du router. Pas besoin de jarvis-llm.
- gRPC (--via-grpc) : passe par le service jarvis-llm:50052. Note : le mode
  gRPC est mono-tour pour l'instant (Complete RPC ne prend qu'un prompt + system).

Backends :
- ollama (défaut) : Ollama HTTP, modèle qwen3:14b par défaut (think=False)
- hf : transformers in-process, Qwen/Qwen2.5-Coder-7B-Instruct par défaut

Usage :
    python -m orchestrator.chat                                   # défaut
    python -m orchestrator.chat --ollama-model gpt-oss:120b       # top qualité
    python -m orchestrator.chat --backend hf                      # backend HF
    python -m orchestrator.chat --no-history                      # mono-tour, pas de mémoire
    python -m orchestrator.chat --history-window 40               # garder 40 messages au lieu de 20
    python -m orchestrator.chat --via-grpc                        # via jarvis-llm:50052

Commandes spéciales :
    /quit, /exit, Ctrl+C    -> sortir
    /reset                  -> efface l'historique (mémoire + disque)
    /history                -> affiche l'historique courant
    /model                  -> affiche le modèle utilisé
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys

from jarvis_llm.clients.huggingface_client import DEFAULT_HF_MODEL, HuggingFaceClient
from jarvis_llm.clients.ollama_client import DEFAULT_LOCAL_MODEL, OllamaClient
from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import LlmBackend, LlmRouter
from orchestrator.clients import llm_client as grpc_llm_client
from orchestrator.conversation import Conversation
from orchestrator.projects.commands import cmd_idee, cmd_projects, cmd_standup, cmd_status

DEFAULT_BACKEND = "ollama"
DEFAULT_HISTORY_WINDOW = 20
HISTORY_PREVIEW_CHARS = 200
DEFAULT_SYSTEM_PROMPT = (
    "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
    "français (sauf si l'utilisateur écrit en anglais), sans phrases creuses, "
    "et tu vas droit au but. Tu peux refuser poliment ce que tu ne sais pas faire. "
    "Tu te souviens des messages précédents dans cette conversation."
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


async def _answer_in_process(
    router: LlmRouter,
    conversation: Conversation,
    user_msg: str,
) -> tuple[str, str, str]:
    """Ajoute le user_msg à l'historique, appelle le LLM, ajoute la réponse."""
    conversation.add_user(user_msg)
    intent = classify(user_msg)
    result = await router.chat(conversation.as_messages(), intent, max_tokens=1024)
    conversation.add_assistant(result.text)
    return result.text, result.model, result.intent.value


def _answer_via_grpc(prompt: str, address: str) -> tuple[str, str, str]:
    """Mode gRPC actuel = mono-tour (Complete RPC). Historique pas propagé."""
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


def _print_banner(
    *,
    via_grpc: bool,
    backend: str,
    model: str,
    history_enabled: bool,
    turns_loaded: int,
) -> None:
    mode = "gRPC (jarvis-llm)" if via_grpc else "in-process"
    history_status = (
        "off (mono-tour)" if not history_enabled else f"on ({turns_loaded} tours chargés)"
    )
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│  Jarvis MVP — chat texte (100% local, multi-tour)           │")
    print(f"│  mode      : {mode:<46}│")
    print(f"│  backend   : {backend:<46}│")
    print(f"│  model     : {model:<46}│")
    print(f"│  historique: {history_status:<46}│")
    print("│  /quit /reset /history /model                               │")
    print("│  /projects /status <nom> /standup /idee <texte>             │")
    print("└─────────────────────────────────────────────────────────────┘")


def _show_history(conversation: Conversation) -> None:
    msgs = conversation.messages()
    if not msgs:
        print("(historique vide)")
        return
    print(f"(historique : {len(msgs)} messages)")
    for m in msgs:
        prefix = "Vous>   " if m.role == "user" else "Jarvis> "
        # Tronque les longs messages pour rester lisible
        content = m.content
        if len(content) >= HISTORY_PREVIEW_CHARS:
            content = content[:HISTORY_PREVIEW_CHARS] + "..."
        print(f"  {prefix}{content}")


def _handle_special_command(
    user: str,
    conversation: Conversation | None,
    last_model: str,
) -> bool:
    """Retourne True si la ligne user était une commande gérée (REPL doit `continue`)."""
    cmd_lower = user.lower()
    if cmd_lower in {"/quit", "/exit", "exit", "quit"}:
        print("👋 Bye.")
        raise SystemExit(0)
    if _handle_session_command(cmd_lower, conversation, last_model):
        return True
    return _handle_project_command(user, cmd_lower)


def _handle_session_command(
    cmd_lower: str,
    conversation: Conversation | None,
    last_model: str,
) -> bool:
    """Commandes liées à la session courante (/reset, /history, /model)."""
    if cmd_lower == "/reset":
        if conversation is None:
            print("(historique désactivé)")
        else:
            conversation.reset()
            print("✅ Historique effacé (mémoire + disque).")
        return True
    if cmd_lower == "/history":
        if conversation is None:
            print("(historique désactivé)")
        else:
            _show_history(conversation)
        return True
    if cmd_lower == "/model":
        print(f"Dernier modèle : {last_model}")
        return True
    return False


def _handle_project_command(user: str, cmd_lower: str) -> bool:
    """Commandes liées à la gestion projet (/projects, /status, /standup, /idee)."""
    if cmd_lower == "/projects":
        print(cmd_projects())
        return True
    if cmd_lower == "/standup":
        print(cmd_standup())
        return True
    if cmd_lower.startswith("/status"):
        parts = user.split(maxsplit=1)
        if len(parts) < 2:
            print("Usage : /status <nom-projet>")
        else:
            print(cmd_status(parts[1].strip()))
        return True
    if cmd_lower.startswith("/idee"):
        parts = user.split(maxsplit=1)
        text = parts[1].strip() if len(parts) > 1 else ""
        print(cmd_idee(text))
        return True
    return False


def _dispatch_user_message(
    user: str,
    *,
    via_grpc: bool,
    grpc_address: str,
    router: LlmRouter | None,
    conversation: Conversation | None,
    loop: asyncio.AbstractEventLoop,
) -> tuple[str, str, str]:
    """Route le message utilisateur vers gRPC ou in-process, avec ou sans historique.

    On utilise une event loop persistante passée par le REPL (`loop.run_until_complete`)
    plutôt qu'`asyncio.run` à chaque appel. Sans ça, sur Windows, httpx/anyio
    (utilisés par `ollama.AsyncClient`) ne nettoient pas leurs sockets entre les
    fermetures de loop → RuntimeError "Event loop is closed" au 2e tour.
    """
    if via_grpc:
        return _answer_via_grpc(user, address=grpc_address)
    if conversation is not None:
        assert router is not None
        return loop.run_until_complete(_answer_in_process(router, conversation, user))
    # Mode --no-history en in-process : tour isolé sans persistance
    assert router is not None
    tmp_conv = Conversation(system_prompt=DEFAULT_SYSTEM_PROMPT, window=2, path=None)
    return loop.run_until_complete(_answer_in_process(router, tmp_conv, user))


def run_repl(
    *,
    via_grpc: bool,
    backend: str,
    ollama_model: str,
    hf_model: str,
    quantize_4bit: bool,
    grpc_address: str,
    history_enabled: bool,
    history_window: int,
) -> int:
    router: LlmRouter | None = None
    if not via_grpc:
        router = _build_in_process_router(
            backend=backend,
            ollama_model=ollama_model,
            hf_model=hf_model,
            quantize_4bit=quantize_4bit,
        )

    # Conversation : path par défaut auto-détecté (.local/conversation.json à la racine
    # du repo). path=None désactive la persistance.
    if history_enabled and not via_grpc:
        conversation: Conversation | None = Conversation(
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            window=history_window,
        )
    else:
        conversation = None

    display_model = ollama_model if backend == "ollama" else hf_model
    turns_loaded = conversation.turn_count() if conversation is not None else 0
    _print_banner(
        via_grpc=via_grpc,
        backend=backend,
        model=display_model,
        history_enabled=conversation is not None,
        turns_loaded=turns_loaded,
    )
    if backend == "hf" and not via_grpc:
        print("(1er appel HF : chargement modèle, peut prendre 30s à 2min…)", file=sys.stderr)

    last_model = display_model

    # Event loop persistante pour toute la durée du REPL.
    # Sans ça : RuntimeError "Event loop is closed" au 2e tour sur Windows
    # car httpx/anyio (côté ollama.AsyncClient) ne ferment pas leurs sockets
    # à temps quand on enchaîne plusieurs `asyncio.run(...)`.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return _repl_loop(
            loop=loop,
            via_grpc=via_grpc,
            grpc_address=grpc_address,
            router=router,
            conversation=conversation,
            last_model=last_model,
        )
    finally:
        with contextlib.suppress(Exception):
            loop.close()


def _repl_loop(
    *,
    loop: asyncio.AbstractEventLoop,
    via_grpc: bool,
    grpc_address: str,
    router: LlmRouter | None,
    conversation: Conversation | None,
    last_model: str,
) -> int:
    while True:
        try:
            user = input("\nVous> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye.")
            return 0

        if not user:
            continue

        try:
            if _handle_special_command(user, conversation, last_model):
                continue
        except SystemExit as exc:
            return int(exc.code or 0)

        try:
            text, used_model, intent = _dispatch_user_message(
                user,
                via_grpc=via_grpc,
                grpc_address=grpc_address,
                router=router,
                conversation=conversation,
                loop=loop,
            )
        except Exception as exc:
            print(f"❌ Erreur : {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        last_model = used_model
        print(f"\nJarvis> {text}")
        print(f"  ↳ model={used_model} intent={intent}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="REPL de chat Jarvis (MVP texte multi-tour, 100% local)",
    )
    parser.add_argument(
        "--via-grpc",
        action="store_true",
        help="passe par le service jarvis-llm distant (gRPC, mono-tour pour l'instant)",
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
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="désactive l'historique conversationnel (mode mono-tour comme avant)",
    )
    parser.add_argument(
        "--history-window",
        type=int,
        default=DEFAULT_HISTORY_WINDOW,
        help=f"nombre max de messages user/assistant à garder (défaut {DEFAULT_HISTORY_WINDOW})",
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
            history_enabled=not args.no_history,
            history_window=args.history_window,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
