"""Tests du helper secrets (priorité keyring > env)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from jarvis_llm import secrets


def test_get_returns_keyring_value_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_keyring = type("FakeKeyring", (), {})()
    fake_keyring.get_password = lambda service, key: "sk-ant-from-keyring"

    with patch.dict("sys.modules", {"keyring": fake_keyring}):
        assert secrets.get_anthropic_api_key() == "sk-ant-from-keyring"


def test_get_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    fake_keyring = type("FakeKeyring", (), {})()
    fake_keyring.get_password = lambda service, key: None

    with patch.dict("sys.modules", {"keyring": fake_keyring}):
        assert secrets.get_anthropic_api_key() == "sk-ant-from-env"


def test_get_returns_none_when_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_keyring = type("FakeKeyring", (), {})()
    fake_keyring.get_password = lambda service, key: None

    with patch.dict("sys.modules", {"keyring": fake_keyring}):
        assert secrets.get_anthropic_api_key() is None


def test_require_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_keyring = type("FakeKeyring", (), {})()
    fake_keyring.get_password = lambda service, key: None

    with (
        patch.dict("sys.modules", {"keyring": fake_keyring}),
        pytest.raises(RuntimeError, match="Anthropic"),
    ):
        secrets.require_anthropic_api_key()
