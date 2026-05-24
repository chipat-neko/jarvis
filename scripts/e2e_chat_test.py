"""Test E2E manuel d'un backend LLM Jarvis.

Lance 4 prompts standards via le backend choisi et affiche pour chacun :
    - le temps total
    - les tokens consommés
    - la réponse complète (utf-8)

Conçu pour être lancé en non-interactif depuis Claude, avec timeout par prompt.
Si un prompt dépasse `PER_PROMPT_TIMEOUT_S` secondes, on l'avorte et on continue.

Usage :
    py -3.11 -O scripts/e2e_chat_test.py --backend ollama
    py -3.11 -O scripts/e2e_chat_test.py --backend hf --hf-model Qwen/Qwen2.5-Coder-3B-Instruct
    py -3.11 -O scripts/e2e_chat_test.py --backend hf --hf-model Qwen/Qwen2.5-Coder-7B-Instruct
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
    "français, sans phrases creuses, droit au but."
)

PROMPTS = [
    ("smalltalk", "Bonjour Jarvis, comment vas-tu aujourd'hui ?"),
    ("simple", "Quelle est la capitale de la France ?"),
    (
        "code",
        "Écris une fonction Python `fib(n)` qui retourne le n-ième nombre de Fibonacci, sans récursion.",
    ),
    (
        "reasoning",
        "J'ai 3 pommes. J'en mange 1, puis j'en achète 2. Combien j'en ai au final ? Détaille en 2 phrases max.",
    ),
]

PER_PROMPT_TIMEOUT_S = 240  # 4 min max par prompt (gros modèle gpt-oss:120b est lent)


def banner(text: str) -> None:
    print(f"\n{'=' * 70}", flush=True)
    print(f"  {text}", flush=True)
    print("=" * 70, flush=True)


async def run_one(router: LlmRouter, label: str, prompt: str, index: int, total: int) -> None:
    intent = classify(prompt)
    print(
        f"\n[{index}/{total}] label={label} intent={intent.value}",
        flush=True,
    )
    print(f"  prompt: {prompt}", flush=True)
    print(f"  start : {time.strftime('%H:%M:%S')}", flush=True)
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            router.execute(prompt, intent, system=SYSTEM, max_tokens=400),
            timeout=PER_PROMPT_TIMEOUT_S,
        )
    except TimeoutError:
        elapsed = time.monotonic() - start
        print(
            f"  TIMEOUT après {elapsed:.1f}s (limite {PER_PROMPT_TIMEOUT_S}s) — prompt skipped",
            flush=True,
        )
        return
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"  ERROR après {elapsed:.1f}s : {type(exc).__name__}: {exc}", flush=True)
        return

    elapsed = time.monotonic() - start
    tok_in = result.input_tokens
    tok_out = result.output_tokens
    tok_per_s = tok_out / elapsed if elapsed > 0 else 0
    print(f"  end   : {time.strftime('%H:%M:%S')} (elapsed {elapsed:.1f}s)", flush=True)
    print(f"  model : {result.model}", flush=True)
    print(f"  tokens: {tok_in} -> {tok_out}  ({tok_per_s:.1f} tok/s)", flush=True)
    print("  --- reponse ---", flush=True)
    print(result.text, flush=True)
    print("  --- fin ---", flush=True)


async def amain(backend: LlmBackend) -> None:
    router = LlmRouter(backend=backend)
    for i, (label, prompt) in enumerate(PROMPTS, start=1):
        await run_one(router, label, prompt, i, len(PROMPTS))


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E test runner for Jarvis LLM backends")
    parser.add_argument("--backend", choices=["ollama", "hf"], required=True)
    parser.add_argument("--ollama-model", default="gpt-oss:120b")
    parser.add_argument("--hf-model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--quantize-4bit", action="store_true")
    args = parser.parse_args()

    if args.backend == "ollama":
        backend: LlmBackend = OllamaClient(model=args.ollama_model)
        banner(f"E2E test  ::  backend=ollama  model={args.ollama_model}")
    else:
        backend = HuggingFaceClient(model_id=args.hf_model, quantize_4bit=args.quantize_4bit)
        banner(f"E2E test  ::  backend=hf  model={args.hf_model}  4bit={args.quantize_4bit}")

    asyncio.run(amain(backend))
    banner("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
