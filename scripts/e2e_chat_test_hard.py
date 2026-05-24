"""Test E2E poussé d'un backend LLM Jarvis.

10 prompts variés (chat, code, debug, reasoning multi-étape, format JSON,
EN, factuel, créativité, technique avancé, edge-case) pour stresser un
backend bien plus sérieusement que `e2e_chat_test.py`.

Usage :
    py -3.11 scripts/e2e_chat_test_hard.py --backend ollama
    py -3.11 scripts/e2e_chat_test_hard.py --backend hf --hf-model Qwen/Qwen2.5-Coder-3B-Instruct
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from jarvis_llm.clients.huggingface_client import HuggingFaceClient
from jarvis_llm.clients.ollama_client import OllamaClient
from jarvis_llm.intent_classifier import classify
from jarvis_llm.router import LlmBackend, LlmRouter

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SYSTEM = (
    "Tu es Jarvis, un assistant personnel concis et précis. Tu réponds en "
    "français (sauf si l'utilisateur écrit en anglais), sans phrases creuses, "
    "et tu vas droit au but. Pour le code, donne un exemple complet, fonctionnel, "
    "sans paraphrase inutile."
)

# 10 prompts allant du smalltalk au reasoning complexe.
PROMPTS: list[tuple[str, str, int]] = [
    (
        "01-presentation",
        "Présente-toi en 3 phrases qui mettent en avant ce que tu sais bien faire.",
        300,
    ),
    (
        "02-code-dedup",
        "Implémente une fonction Python `dedup_preserving_order(items)` qui retire "
        "les doublons d'une liste en conservant l'ordre d'apparition. Inclus un docstring "
        "et 2 exemples d'usage dans des commentaires.",
        500,
    ),
    (
        "03-debug",
        "Voici un bout de code qui plante. Trouve le bug et corrige-le. Donne le code "
        "corrigé et explique en 1 phrase ce qui n'allait pas :\n"
        "```python\n"
        "def moyenne(nombres):\n"
        "    return sum(nombres) / len(nombres)\n"
        "\n"
        "print(moyenne([]))\n"
        "```",
        500,
    ),
    (
        "04-reasoning-multi",
        "J'ai 12 cartes. J'en donne la moitié à un ami. Sur celles qu'il me reste, "
        "j'en perds 2. Puis j'achète 3 paquets de 4 cartes chacun. Combien j'en ai au "
        "final ? Détaille étape par étape, puis donne le total.",
        400,
    ),
    (
        "05-conversion-temps",
        "Combien de minutes y a-t-il dans 2,5 jours ? Réponds par le nombre puis "
        "une phrase de justification.",
        150,
    ),
    (
        "06-json-strict",
        "Donne-moi 3 idées d'apéros faciles au format JSON STRICT (un seul objet "
        "racine avec une clé `aperos` qui contient un array de 3 objets). Chaque objet "
        "doit avoir les clés exactes : `nom` (string), `ingredients` (array de strings), "
        "`temps_prep_min` (number). Aucune balise markdown autour, juste le JSON.",
        400,
    ),
    (
        "07-english",
        "In English: Explain in 2 sentences what a Python decorator is, and give one "
        "tiny working example with @timer that prints how long a function took.",
        400,
    ),
    (
        "08-security-legit",
        "Je veux vérifier les ports ouverts SUR MON PROPRE PC en local (127.0.0.1). "
        "Donne-moi un script Python court (stdlib uniquement) qui scanne les ports "
        "20-100 et affiche ceux qui sont ouverts.",
        500,
    ),
    (
        "09-python-init",
        "Quelle est la différence entre un `__init__.py` vide et son absence totale "
        "dans un dossier en Python 3.3+ ? Réponds en 2-3 phrases max, sans exemple "
        "de code.",
        250,
    ),
    (
        "10-creative",
        "Propose-moi 3 noms originaux et fun pour un chat noir et blanc. Pour chacun, "
        "donne le nom en gras puis une phrase courte expliquant l'idée derrière.",
        400,
    ),
]

PER_PROMPT_TIMEOUT_S = 360  # 6 min max (gpt-oss:120b reasoning peut être long)
PROMPT_PREVIEW_CHARS = 120


def banner(text: str) -> None:
    print(f"\n{'=' * 78}", flush=True)
    print(f"  {text}", flush=True)
    print("=" * 78, flush=True)


async def run_one(
    router: LlmRouter, label: str, prompt: str, max_tokens: int, index: int, total: int
) -> dict:
    intent = classify(prompt)
    print(
        f"\n[{index:>2}/{total}] {label}  intent={intent.value}  max_tokens={max_tokens}",
        flush=True,
    )
    preview = prompt[:PROMPT_PREVIEW_CHARS]
    if len(prompt) > PROMPT_PREVIEW_CHARS:
        preview += "..."
    print(f"  prompt: {preview}", flush=True)
    print(f"  start : {time.strftime('%H:%M:%S')}", flush=True)
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            router.execute(prompt, intent, system=SYSTEM, max_tokens=max_tokens),
            timeout=PER_PROMPT_TIMEOUT_S,
        )
    except TimeoutError:
        elapsed = time.monotonic() - start
        print(
            f"  TIMEOUT après {elapsed:.1f}s (limite {PER_PROMPT_TIMEOUT_S}s)",
            flush=True,
        )
        return {"label": label, "ok": False, "reason": "timeout", "elapsed": elapsed}
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"  ERROR après {elapsed:.1f}s : {type(exc).__name__}: {exc}", flush=True)
        return {"label": label, "ok": False, "reason": str(exc), "elapsed": elapsed}

    elapsed = time.monotonic() - start
    tok_out = result.output_tokens
    tok_per_s = tok_out / elapsed if elapsed > 0 else 0
    print(f"  end   : {time.strftime('%H:%M:%S')} ({elapsed:.1f}s)", flush=True)
    print(
        f"  model : {result.model}  tokens: {result.input_tokens}->{tok_out}  ({tok_per_s:.1f} tok/s)",
        flush=True,
    )
    print("  --- reponse ---", flush=True)
    print(result.text, flush=True)
    print("  --- fin ---", flush=True)
    return {
        "label": label,
        "ok": True,
        "elapsed": elapsed,
        "tok_in": result.input_tokens,
        "tok_out": tok_out,
        "tok_per_s": tok_per_s,
    }


async def amain(backend: LlmBackend) -> None:
    router = LlmRouter(backend=backend)
    results = []
    for i, (label, prompt, mt) in enumerate(PROMPTS, start=1):
        r = await run_one(router, label, prompt, mt, i, len(PROMPTS))
        results.append(r)

    banner("RÉSUMÉ")
    ok = sum(1 for r in results if r["ok"])
    total_time = sum(r["elapsed"] for r in results)
    total_out = sum(r.get("tok_out", 0) for r in results if r["ok"])
    print(f"  Réussis : {ok}/{len(results)}", flush=True)
    print(f"  Temps total cumul : {total_time:.1f}s", flush=True)
    print(f"  Tokens out total : {total_out}", flush=True)
    print(f"  Vitesse moyenne : {total_out / total_time:.1f} tok/s", flush=True)
    print("\n  Par prompt :", flush=True)
    for r in results:
        if r["ok"]:
            print(
                f"    {r['label']:>22}  {r['elapsed']:>5.1f}s  {r['tok_out']:>4} tok  "
                f"{r['tok_per_s']:>5.1f} tok/s",
                flush=True,
            )
        else:
            print(f"    {r['label']:>22}  FAIL ({r['reason']})", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E test hard runner for Jarvis")
    parser.add_argument("--backend", choices=["ollama", "hf"], required=True)
    parser.add_argument("--ollama-model", default="qwen3:14b")
    parser.add_argument("--hf-model", default="Qwen/Qwen2.5-Coder-3B-Instruct")
    parser.add_argument("--quantize-4bit", action="store_true")
    args = parser.parse_args()

    if args.backend == "ollama":
        backend: LlmBackend = OllamaClient(model=args.ollama_model)
        banner(f"E2E HARD :: backend=ollama model={args.ollama_model}")
    else:
        backend = HuggingFaceClient(model_id=args.hf_model, quantize_4bit=args.quantize_4bit)
        banner(f"E2E HARD :: backend=hf model={args.hf_model} 4bit={args.quantize_4bit}")

    asyncio.run(amain(backend))
    banner("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
