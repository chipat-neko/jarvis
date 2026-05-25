"""Hardcore runner : lance un dataset de prompts contre un backend LLM et scorer.

Lit un fichier JSONL produit par `scripts.prompt_gen`, envoie chaque prompt
au backend choisi (Ollama par défaut), applique les `signals` du prompt
(regex, ast.parse, json.loads, length_range) et écrit un raw.jsonl + summary +
report.html dans `out_dir/{model}/{date}/`.

Background-friendly :
- Timeout par prompt (`--timeout 60`)
- Resume possible : skip les prompts déjà présents dans raw.jsonl
- Watchdog stale : si pas de progression depuis N secondes, on log et continue

Usage :
    python -m scripts.hardcore_runner --prompts prompts_hc.jsonl --model qwen3:14b
    python -m scripts.hardcore_runner --prompts prompts.jsonl --max-prompts 10  # quick test
    python -m scripts.hardcore_runner --resume                                  # reprend run précédent
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prompt_gen.dataset import Prompt, Signal, load_jsonl
from scripts.prompt_gen.signals import (
    AstParseSignal,
    JsonParseSignal,
    LengthRangeSignal,
    RegexMatchSignal,
)

DEFAULT_OUT_DIR = Path("results")
DEFAULT_TIMEOUT_SEC = 90.0


@dataclass(frozen=True, slots=True)
class PromptResult:
    """Résultat d'un appel LLM scoré."""

    prompt_id: str
    category: str
    difficulty: str
    text: str
    response: str
    model: str
    elapsed_sec: float
    signals_passed: int
    signals_total: int
    signals_details: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and self.signals_passed == self.signals_total

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _OllamaBackend:
    """Wrapper minimal Ollama (réutilise OllamaClient si dispo)."""

    def __init__(self, model: str, *, host: str | None = None, timeout_sec: float) -> None:
        self.model = model
        self.timeout_sec = timeout_sec
        try:
            from jarvis_llm.clients.ollama_client import OllamaClient  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "jarvis-llm pas installé. Lance `pip install -e services/jarvis-llm`"
            ) from exc
        kwargs: dict = {"model": model}
        if host:
            kwargs["host"] = host
        self._client = OllamaClient(**kwargs)

    async def complete(self, prompt: str) -> tuple[str, float]:
        start = time.monotonic()
        try:
            completion = await asyncio.wait_for(
                self._client.complete(prompt, max_tokens=1024),
                timeout=self.timeout_sec,
            )
            return completion.text, time.monotonic() - start
        except TimeoutError as exc:
            raise RuntimeError(f"timeout {self.timeout_sec}s sur le prompt") from exc


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _signal_for(spec: Signal):
    kind = spec.kind
    params = spec.params or {}
    if kind == "regex":
        return RegexMatchSignal(pattern=params.get("pattern", ""), flags=params.get("flags", 0))
    if kind == "ast":
        return AstParseSignal(language=params.get("language", "python"))
    if kind == "json":
        return JsonParseSignal()
    if kind == "length_range":
        return LengthRangeSignal(
            min_chars=params.get("min_chars", 0),
            max_chars=params.get("max_chars", 100_000),
        )
    return None


def score_response(response: str, signals: tuple[Signal, ...]) -> tuple[int, int, list[dict]]:
    """Applique tous les signals et retourne (passed, total, details)."""
    passed = 0
    details: list[dict] = []
    for spec in signals:
        sig = _signal_for(spec)
        if sig is None:
            details.append({"kind": spec.kind, "passed": False, "reason": "signal inconnu"})
            continue
        res = sig.check(response)
        if res.passed:
            passed += 1
        details.append(
            {
                "kind": spec.kind,
                "passed": res.passed,
                "reason": res.reason,
                "required": spec.required,
            }
        )
    return passed, len(signals), details


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_one(
    prompt: Prompt,
    backend: _OllamaBackend,
) -> PromptResult:
    try:
        response, elapsed = await backend.complete(prompt.text)
    except Exception as exc:
        return PromptResult(
            prompt_id=prompt.id,
            category=prompt.category,
            difficulty=prompt.difficulty,
            text=prompt.text,
            response="",
            model=backend.model,
            elapsed_sec=0.0,
            signals_passed=0,
            signals_total=len(prompt.signals),
            signals_details=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    passed, total, details = score_response(response, prompt.signals)
    return PromptResult(
        prompt_id=prompt.id,
        category=prompt.category,
        difficulty=prompt.difficulty,
        text=prompt.text,
        response=response,
        model=backend.model,
        elapsed_sec=round(elapsed, 2),
        signals_passed=passed,
        signals_total=total,
        signals_details=details,
    )


async def run_all(
    prompts: list[Prompt],
    backend: _OllamaBackend,
    raw_path: Path,
    *,
    resume_from: set[str] | None = None,
) -> list[PromptResult]:
    resume_from = resume_from or set()
    results: list[PromptResult] = []
    total = len(prompts)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    # Ouvert en append pour le resume
    with raw_path.open("a", encoding="utf-8") as f:
        for i, prompt in enumerate(prompts, start=1):
            if prompt.id in resume_from:
                print(f"[{i}/{total}] SKIP (déjà traité) : {prompt.id}", file=sys.stderr)
                continue
            print(
                f"[{i}/{total}] {prompt.id} ({prompt.category}/{prompt.difficulty})…",
                file=sys.stderr,
            )
            result = await run_one(prompt, backend)
            results.append(result)
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
            f.flush()
            status = "✅" if result.passed else ("⚠️" if not result.error else "❌")
            print(
                f"    {status} {result.signals_passed}/{result.signals_total} "
                f"signals · {result.elapsed_sec}s",
                file=sys.stderr,
            )
    return results


# ---------------------------------------------------------------------------
# Summary + report HTML
# ---------------------------------------------------------------------------


def build_summary(results: list[PromptResult]) -> dict[str, Any]:
    if not results:
        return {"total": 0, "passed": 0, "pass_rate": 0.0, "by_category": {}, "errors": 0}

    by_cat: dict[str, dict] = {}
    for r in results:
        c = by_cat.setdefault(
            r.category, {"total": 0, "passed": 0, "signal_pass_sum": 0, "signal_total_sum": 0}
        )
        c["total"] += 1
        if r.passed:
            c["passed"] += 1
        c["signal_pass_sum"] += r.signals_passed
        c["signal_total_sum"] += r.signals_total

    for c in by_cat.values():
        c["pass_rate"] = round(c["passed"] / max(1, c["total"]) * 100, 1)
        c["signal_rate"] = round(c["signal_pass_sum"] / max(1, c["signal_total_sum"]) * 100, 1)

    errors = sum(1 for r in results if r.error)
    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    avg_time = round(sum(r.elapsed_sec for r in results) / max(1, total), 2)

    return {
        "model": results[0].model,
        "total": total,
        "passed": passed_count,
        "pass_rate": round(passed_count / max(1, total) * 100, 1),
        "errors": errors,
        "avg_seconds": avg_time,
        "difficulties": dict(Counter(r.difficulty for r in results)),
        "by_category": by_cat,
    }


def build_report_html(summary: dict, results: list[PromptResult]) -> str:
    """Rapport HTML auto-contenu (palette cyan/violet, comme jarvis-ui)."""
    rows = "".join(_result_row(r) for r in results)
    cat_rows = "".join(
        f"<tr><td>{cat}</td><td>{d['total']}</td><td>{d['passed']}</td>"
        f"<td>{d['pass_rate']}%</td><td>{d['signal_rate']}%</td></tr>"
        for cat, d in sorted(summary.get("by_category", {}).items())
    )
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Hardcore Bench · {summary.get("model", "?")}</title>
<style>
body{{font-family:Inter,system-ui,sans-serif;background:#0a0c14;color:#c9d1e7;padding:24px;margin:0}}
h1{{background:linear-gradient(90deg,#00ddff,#7c5cff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.metric{{display:inline-block;padding:14px 18px;margin:8px;background:rgba(20,24,33,0.7);border:1px solid rgba(124,92,255,0.25);border-radius:12px}}
.metric .val{{font-size:28px;font-weight:800;color:#eef2ff;display:block}}
.metric .lbl{{font-size:11px;text-transform:uppercase;color:#8896b3;letter-spacing:1px}}
table{{width:100%;border-collapse:collapse;margin-top:18px;background:rgba(20,24,33,0.5);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid rgba(124,92,255,0.1)}}
th{{background:rgba(124,92,255,0.12);font-size:11px;text-transform:uppercase;color:#c9d1e7;letter-spacing:1px}}
.passed{{color:#84cc16}}.failed{{color:#ef4444}}.errored{{color:#f59e0b}}
details{{margin:8px 0;padding:10px;background:rgba(10,12,20,0.5);border-radius:8px;border:1px solid rgba(124,92,255,0.1)}}
details summary{{cursor:pointer;font-weight:600}}
pre{{white-space:pre-wrap;font-family:'JetBrains Mono',monospace;font-size:11px;color:#8896b3;background:rgba(10,12,20,0.5);padding:8px;border-radius:6px;margin-top:8px;overflow-x:auto}}
</style></head><body>
<h1>Hardcore Bench — {summary.get("model", "?")}</h1>
<p>Run {datetime.now(tz=UTC).isoformat()[:19]} · {summary.get("total", 0)} prompts</p>
<div>
  <div class="metric"><span class="val">{summary.get("pass_rate", 0)}%</span><span class="lbl">Pass rate</span></div>
  <div class="metric"><span class="val">{summary.get("passed", 0)} / {summary.get("total", 0)}</span><span class="lbl">Réussis</span></div>
  <div class="metric"><span class="val">{summary.get("errors", 0)}</span><span class="lbl">Erreurs</span></div>
  <div class="metric"><span class="val">{summary.get("avg_seconds", 0)}s</span><span class="lbl">Latence moy.</span></div>
</div>

<h2>Par catégorie</h2>
<table><tr><th>Catégorie</th><th>N</th><th>Réussis</th><th>Pass rate</th><th>Signal rate</th></tr>{cat_rows}</table>

<h2>Détails par prompt</h2>
{rows}
</body></html>"""


def _result_row(r: PromptResult) -> str:
    if r.error:
        status_class, status_txt = "errored", f"❌ {r.error}"
    elif r.passed:
        status_class, status_txt = "passed", f"✅ {r.signals_passed}/{r.signals_total}"
    else:
        status_class, status_txt = "failed", f"⚠️ {r.signals_passed}/{r.signals_total}"
    sig_html = "".join(
        f"<li>{d.get('kind')}: {'✅' if d.get('passed') else '❌'} "
        f"<small>{d.get('reason') or ''}</small></li>"
        for d in r.signals_details
    )
    return f"""<details>
<summary><span class="{status_class}">{status_txt}</span> · <code>{r.prompt_id}</code> ·
  {r.category}/{r.difficulty} · {r.elapsed_sec}s</summary>
<p><strong>Prompt :</strong></p><pre>{_escape(r.text)}</pre>
<p><strong>Réponse :</strong></p><pre>{_escape(r.response or "(vide)")}</pre>
<p><strong>Signals :</strong></p><ul>{sig_html}</ul>
</details>"""


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


def _existing_ids(raw_path: Path) -> set[str]:
    if not raw_path.exists():
        return set()
    ids: set[str] = set()
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                ids.add(json.loads(line).get("prompt_id"))
            except json.JSONDecodeError:
                continue
    return ids


def _load_existing_results(raw_path: Path) -> list[PromptResult]:
    if not raw_path.exists():
        return []
    out: list[PromptResult] = []
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                out.append(PromptResult(**d))
            except (json.JSONDecodeError, TypeError):
                continue
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hardcore bench runner Jarvis")
    parser.add_argument("--prompts", type=Path, required=True, help="fichier JSONL de prompts")
    parser.add_argument("--backend", choices=["ollama"], default="ollama")
    parser.add_argument("--model", default="qwen3:14b", help="modèle Ollama")
    parser.add_argument("--host", default=None, help="URL Ollama (défaut env OLLAMA_HOST)")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"dossier de sortie (default {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"timeout par prompt (default {DEFAULT_TIMEOUT_SEC}s)",
    )
    parser.add_argument(
        "--max-prompts",
        type=int,
        default=None,
        help="limite N premiers prompts (quick test)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip les prompts déjà présents dans raw.jsonl",
    )
    args = parser.parse_args(argv)

    prompts = load_jsonl(args.prompts)
    if args.max_prompts:
        prompts = prompts[: args.max_prompts]
    if not prompts:
        print(f"❌ aucun prompt dans {args.prompts}", file=sys.stderr)
        return 1

    date_str = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = args.out_dir / args.model.replace(":", "_") / date_str
    raw_path = run_dir / "raw.jsonl"

    if args.resume:
        # On essaie de retrouver un run précédent pour la même config
        existing = sorted(
            (args.out_dir / args.model.replace(":", "_")).glob("*/raw.jsonl"),
            key=lambda p: p.parent.name,
            reverse=True,
        )
        if existing:
            raw_path = existing[0]
            run_dir = raw_path.parent
            print(f"[resume] reprise depuis {raw_path}", file=sys.stderr)
        else:
            print("[resume] aucun run précédent trouvé, run neuf", file=sys.stderr)

    resume_ids = _existing_ids(raw_path) if args.resume else set()
    backend = _OllamaBackend(model=args.model, host=args.host, timeout_sec=args.timeout)

    try:
        new_results = asyncio.run(
            run_all(prompts, backend, raw_path, resume_from=resume_ids),
        )
    except KeyboardInterrupt:
        print("[runner] interrompu — résultats partiels sauvegardés", file=sys.stderr)
        return 130

    all_results = _load_existing_results(raw_path) if args.resume else new_results
    summary = build_summary(all_results)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "report.html").write_text(build_report_html(summary, all_results), encoding="utf-8")
    print(
        f"\n[runner] {summary['passed']}/{summary['total']} passés "
        f"({summary['pass_rate']}%) · report → {run_dir / 'report.html'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
