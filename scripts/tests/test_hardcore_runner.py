"""Tests du hardcore_runner (scoring + summary + report HTML + resume)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.hardcore_runner import (
    PromptResult,
    _existing_ids,
    _load_existing_results,
    build_report_html,
    build_summary,
    score_response,
)
from scripts.prompt_gen.dataset import Signal

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_response_all_pass() -> None:
    signals = (
        Signal(kind="regex", params={"pattern": r"\d+"}),
        Signal(kind="length_range", params={"min_chars": 1, "max_chars": 100}),
    )
    passed, total, details = score_response("réponse: 42", signals)
    assert passed == 2
    assert total == 2
    assert all(d["passed"] for d in details)


def test_score_response_partial() -> None:
    signals = (
        Signal(kind="regex", params={"pattern": r"\d+"}),
        Signal(kind="length_range", params={"min_chars": 1000, "max_chars": 2000}),
    )
    passed, total, _ = score_response("court avec 42", signals)
    assert passed == 1
    assert total == 2


def test_score_response_unknown_signal() -> None:
    signals = (Signal(kind="totally_bogus", params={}),)
    passed, total, details = score_response("anything", signals)
    assert passed == 0
    assert total == 1
    assert details[0]["passed"] is False
    assert "inconnu" in details[0]["reason"]


def test_score_ast_signal_ok() -> None:
    signals = (Signal(kind="ast", params={"language": "python"}),)
    passed, _, _ = score_response("```python\ndef f(): return 1\n```", signals)
    assert passed == 1


def test_score_json_signal_ok() -> None:
    signals = (Signal(kind="json", params={}),)
    passed, _, _ = score_response('voici {"ok": true}', signals)
    assert passed == 1


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _mk_result(
    *, idx: int = 0, category: str = "code", passed: bool, error: str | None = None
) -> PromptResult:
    sigs_passed = 2 if passed else 0
    return PromptResult(
        prompt_id=f"p_{idx:03d}",
        category=category,
        difficulty="L2",
        text="prompt text",
        response="" if error else "response text",
        model="qwen3:14b",
        elapsed_sec=1.0,
        signals_passed=sigs_passed,
        signals_total=2,
        signals_details=[],
        error=error,
    )


def test_summary_empty() -> None:
    summary = build_summary([])
    assert summary == {"total": 0, "passed": 0, "pass_rate": 0.0, "by_category": {}, "errors": 0}


def test_summary_pass_rate() -> None:
    results = [
        _mk_result(idx=0, passed=True),
        _mk_result(idx=1, passed=True),
        _mk_result(idx=2, passed=False),
        _mk_result(idx=3, passed=False, error="timeout"),
    ]
    summary = build_summary(results)
    assert summary["total"] == 4
    assert summary["passed"] == 2
    assert summary["pass_rate"] == 50.0
    assert summary["errors"] == 1
    assert summary["model"] == "qwen3:14b"


def test_summary_by_category() -> None:
    results = [
        _mk_result(idx=0, category="code", passed=True),
        _mk_result(idx=1, category="code", passed=False),
        _mk_result(idx=2, category="math", passed=True),
    ]
    summary = build_summary(results)
    cats = summary["by_category"]
    assert cats["code"]["total"] == 2
    assert cats["code"]["passed"] == 1
    assert cats["code"]["pass_rate"] == 50.0
    assert cats["math"]["pass_rate"] == 100.0


def test_passed_property_only_true_when_all_signals_pass() -> None:
    r_ok = PromptResult(
        prompt_id="x",
        category="c",
        difficulty="L1",
        text="",
        response="r",
        model="m",
        elapsed_sec=0,
        signals_passed=2,
        signals_total=2,
    )
    r_partial = PromptResult(
        prompt_id="x",
        category="c",
        difficulty="L1",
        text="",
        response="r",
        model="m",
        elapsed_sec=0,
        signals_passed=1,
        signals_total=2,
    )
    r_error = PromptResult(
        prompt_id="x",
        category="c",
        difficulty="L1",
        text="",
        response="",
        model="m",
        elapsed_sec=0,
        signals_passed=2,
        signals_total=2,
        error="boom",
    )
    assert r_ok.passed is True
    assert r_partial.passed is False
    assert r_error.passed is False


# ---------------------------------------------------------------------------
# Report HTML
# ---------------------------------------------------------------------------


def test_build_report_html_contains_model_and_metrics() -> None:
    results = [_mk_result(idx=0, passed=True), _mk_result(idx=1, passed=False)]
    summary = build_summary(results)
    html = build_report_html(summary, results)
    assert "qwen3:14b" in html
    assert "Pass rate" in html
    assert "p_000" in html
    assert "p_001" in html


def test_build_report_html_escapes_html_in_response() -> None:
    r = PromptResult(
        prompt_id="x",
        category="c",
        difficulty="L1",
        text="<script>alert(1)</script>",
        response="<img src=x onerror=alert(1)>",
        model="m",
        elapsed_sec=0,
        signals_passed=0,
        signals_total=0,
    )
    summary = build_summary([r])
    html = build_report_html(summary, [r])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


def test_existing_ids_reads_jsonl(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(
        json.dumps({"prompt_id": "a"}) + "\n" + json.dumps({"prompt_id": "b"}) + "\n",
        encoding="utf-8",
    )
    assert _existing_ids(raw) == {"a", "b"}


def test_existing_ids_missing_file(tmp_path: Path) -> None:
    assert _existing_ids(tmp_path / "nope.jsonl") == set()


def test_existing_ids_ignores_corrupted_lines(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(
        json.dumps({"prompt_id": "ok"}) + "\n" + "garbage line\n",
        encoding="utf-8",
    )
    assert _existing_ids(raw) == {"ok"}


def test_load_existing_results_roundtrip(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    r = _mk_result(idx=42, passed=True)
    raw.write_text(json.dumps(r.to_dict()) + "\n", encoding="utf-8")
    loaded = _load_existing_results(raw)
    assert len(loaded) == 1
    assert loaded[0].prompt_id == "p_042"
    assert loaded[0].signals_passed == 2
