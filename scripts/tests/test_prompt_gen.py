"""Tests du module scripts.prompt_gen."""

from __future__ import annotations

from pathlib import Path

from scripts.prompt_gen.dataset import (
    Prompt,
    Signal,
    load_jsonl,
    save_jsonl,
    stratified_sample,
)
from scripts.prompt_gen.generators import generate_all
from scripts.prompt_gen.signals import (
    AstParseSignal,
    JsonParseSignal,
    LengthRangeSignal,
    RegexMatchSignal,
)

# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_regex_match_signal_passes() -> None:
    sig = RegexMatchSignal(pattern=r"\d+")
    assert sig.check("la réponse est 42").passed is True


def test_regex_match_signal_fails() -> None:
    sig = RegexMatchSignal(pattern=r"\d+")
    assert sig.check("aucun chiffre ici").passed is False


def test_regex_match_signal_invalid_pattern() -> None:
    sig = RegexMatchSignal(pattern=r"[unclosed")
    res = sig.check("anything")
    assert res.passed is False
    assert "regex invalide" in (res.reason or "")


def test_ast_parse_signal_python_ok() -> None:
    sig = AstParseSignal(language="python")
    assert sig.check("```python\ndef f():\n    return 1\n```").passed is True


def test_ast_parse_signal_raw_text() -> None:
    sig = AstParseSignal(language="python")
    assert sig.check("x = 1\ny = 2").passed is True


def test_ast_parse_signal_syntax_error() -> None:
    sig = AstParseSignal(language="python")
    res = sig.check("def broken(:\n    pass")
    assert res.passed is False
    assert "SyntaxError" in (res.reason or "")


def test_json_parse_signal_block() -> None:
    sig = JsonParseSignal()
    text = 'voici :\n```json\n{"a": 1, "b": [1,2]}\n```'
    assert sig.check(text).passed is True


def test_json_parse_signal_inline_object() -> None:
    sig = JsonParseSignal()
    assert sig.check('réponse: {"tool": "x"}').passed is True


def test_json_parse_signal_no_json() -> None:
    sig = JsonParseSignal()
    res = sig.check("juste du texte")
    assert res.passed is False


def test_length_range_too_short() -> None:
    sig = LengthRangeSignal(min_chars=10, max_chars=100)
    assert sig.check("court").passed is False


def test_length_range_too_long() -> None:
    sig = LengthRangeSignal(min_chars=0, max_chars=5)
    assert sig.check("xxxxxxxxxx").passed is False


def test_length_range_ok() -> None:
    sig = LengthRangeSignal(min_chars=2, max_chars=20)
    assert sig.check("hello").passed is True


# ---------------------------------------------------------------------------
# Dataset I/O
# ---------------------------------------------------------------------------


def test_save_and_load_jsonl_roundtrip(tmp_path: Path) -> None:
    prompts = [
        Prompt(
            id="t_001",
            category="code",
            difficulty="L1",
            text="Hello",
            signals=(Signal(kind="regex", params={"pattern": r"\w+"}),),
            metadata={"lang": "python"},
        ),
        Prompt(id="t_002", category="math", difficulty="L1", text="2+2 ?"),
    ]
    out = tmp_path / "p.jsonl"
    save_jsonl(prompts, out)
    loaded = load_jsonl(out)
    assert len(loaded) == 2
    assert loaded[0].id == "t_001"
    assert loaded[0].signals[0].kind == "regex"
    assert loaded[1].category == "math"


def test_save_jsonl_handles_unicode(tmp_path: Path) -> None:
    prompts = [Prompt(id="x", category="conversation", difficulty="L1", text="éàç 漢字")]
    out = tmp_path / "u.jsonl"
    save_jsonl(prompts, out)
    loaded = load_jsonl(out)
    assert loaded[0].text == "éàç 漢字"


def test_stratified_sample_keeps_categories_balanced() -> None:
    prompts = [
        Prompt(id=f"c_{i}", category="code", difficulty="L1", text=f"c{i}") for i in range(10)
    ] + [Prompt(id=f"m_{i}", category="math", difficulty="L1", text=f"m{i}") for i in range(10)]
    sample = stratified_sample(prompts, n=6, seed=1)
    assert len(sample) == 6
    cats = {p.category for p in sample}
    assert cats == {"code", "math"}


def test_stratified_sample_deterministic() -> None:
    prompts = [
        Prompt(id=f"c_{i}", category="code", difficulty="L1", text=f"c{i}") for i in range(20)
    ]
    s1 = stratified_sample(prompts, n=5, seed=42)
    s2 = stratified_sample(prompts, n=5, seed=42)
    assert [p.id for p in s1] == [p.id for p in s2]


def test_stratified_sample_returns_all_if_n_larger() -> None:
    prompts = [Prompt(id="a", category="code", difficulty="L1", text="x")]
    sample = stratified_sample(prompts, n=10, seed=0)
    assert len(sample) == 1


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def test_generate_all_produces_requested_count() -> None:
    prompts = generate_all(total=50, seed=42)
    assert len(prompts) == 50


def test_generate_all_is_deterministic() -> None:
    p1 = generate_all(total=20, seed=42)
    p2 = generate_all(total=20, seed=42)
    assert [p.id for p in p1] == [p.id for p in p2]
    assert [p.text for p in p1] == [p.text for p in p2]


def test_generate_all_covers_multiple_categories() -> None:
    prompts = generate_all(total=60, seed=7)
    cats = {p.category for p in prompts}
    # Au moins 4 catégories distinctes sur 6 (la troncature peut en exclure 1-2)
    assert len(cats) >= 4


def test_generate_all_has_valid_difficulty() -> None:
    prompts = generate_all(total=30, seed=42)
    for p in prompts:
        assert p.difficulty in {"L1", "L2", "L3", "L4", "L5"}


def test_generated_prompts_have_non_empty_text() -> None:
    prompts = generate_all(total=30, seed=42)
    for p in prompts:
        assert p.text.strip(), f"Prompt {p.id} a un texte vide"


def test_cli_writes_file(tmp_path: Path) -> None:
    from scripts.prompt_gen.cli import main

    out = tmp_path / "out.jsonl"
    rc = main(["--n", "10", "--seed", "1", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    loaded = load_jsonl(out)
    assert len(loaded) == 10
