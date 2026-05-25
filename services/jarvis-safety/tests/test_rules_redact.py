"""Tests de la redaction des secrets."""

from __future__ import annotations

from jarvis_safety.rules.config import DEFAULT_REDACT_PATTERNS
from jarvis_safety.rules.redact import REDACTED_MARKER, Redactor


def test_anthropic_key_redacted() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    text = "use sk-ant-api03-AAAAaaaa1234567890abcdefgh for the API"
    out = r.redact(text)
    assert "sk-ant" not in out
    assert REDACTED_MARKER in out


def test_github_pat_redacted() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    text = "token ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ012345AbCd"
    out = r.redact(text)
    assert "ghp_" not in out


def test_pem_key_redacted() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    pem = "-----BEGIN PRIVATE KEY-----\nABCDEF\n-----END PRIVATE KEY-----"
    out = r.redact(f"key:\n{pem}\nend")
    assert "ABCDEF" not in out
    assert "-----BEGIN" not in out


def test_safe_text_unchanged() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    text = "Bonjour, comment vas-tu ? Voici du code: def hello(): pass"
    assert r.redact(text) == text


def test_empty_text() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    assert r.redact("") == ""


def test_redact_dict_recursive() -> None:
    r = Redactor(DEFAULT_REDACT_PATTERNS)
    data = {
        "user": "noah",
        "key": "sk-ant-abcdefghijklmnopqrstuvwxyz",
        "nested": {"github_token": "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ012345AbCd"},
        "list": ["ok", "sk-AAAAAAAAAAAAAAAAAAAA"],
    }
    out = r.redact_dict(data)
    assert out["user"] == "noah"
    assert REDACTED_MARKER in out["key"]
    assert REDACTED_MARKER in out["nested"]["github_token"]
    assert "ok" in out["list"]
    assert any(REDACTED_MARKER in s for s in out["list"])


def test_custom_patterns() -> None:
    r = Redactor([r"\bmotdepasse=\S+"])
    text = "user=noah motdepasse=secret123 home=/tmp"
    out = r.redact(text)
    assert "secret123" not in out
    assert "user=noah" in out
    assert "home=/tmp" in out
