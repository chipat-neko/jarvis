"""CLI : génère un dataset JSONL de prompts pour tester Jarvis.

Usage :
    python -m scripts.prompt_gen.cli --n 50 --seed 42 --out prompts.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.prompt_gen.dataset import save_jsonl
from scripts.prompt_gen.generators import generate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génère un dataset JSONL de prompts pour Jarvis.")
    parser.add_argument(
        "--n",
        type=int,
        default=50,
        help="Nombre de prompts à générer (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed pour reproductibilité (default: 42)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("prompts.jsonl"),
        help="Fichier de sortie JSONL (default: prompts.jsonl)",
    )
    args = parser.parse_args(argv)

    prompts = generate_all(total=args.n, seed=args.seed)
    save_jsonl(prompts, args.out)
    print(
        f"[prompt_gen] {len(prompts)} prompts écrits dans {args.out} (seed={args.seed})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
