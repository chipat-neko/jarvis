"""Tests du module orchestrator.conversation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.conversation import (
    DEFAULT_HISTORY_WINDOW,
    Conversation,
    Message,
)


def test_add_user_and_assistant(tmp_path: Path) -> None:
    conv = Conversation(system_prompt="You are Jarvis.", path=tmp_path / "conv.json")
    conv.add_user("Salut")
    conv.add_assistant("Bonjour Noah !")

    msgs = conv.messages()
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Salut"
    assert msgs[1].role == "assistant"
    assert msgs[1].content == "Bonjour Noah !"


def test_as_messages_includes_system_prompt_first(tmp_path: Path) -> None:
    conv = Conversation(system_prompt="You are Jarvis.", path=tmp_path / "conv.json")
    conv.add_user("Hello")
    conv.add_assistant("Hi")

    serialized = conv.as_messages()
    assert serialized[0] == {"role": "system", "content": "You are Jarvis."}
    assert serialized[1] == {"role": "user", "content": "Hello"}
    assert serialized[2] == {"role": "assistant", "content": "Hi"}


def test_sliding_window_keeps_only_last_n(tmp_path: Path) -> None:
    conv = Conversation(system_prompt="sys", window=4, path=tmp_path / "conv.json")
    for i in range(10):
        conv.add_user(f"q{i}")
        conv.add_assistant(f"a{i}")

    msgs = conv.messages()
    # window=4 → on garde les 4 derniers messages = q8, a8, q9, a9
    assert len(msgs) == 4
    assert [m.content for m in msgs] == ["q8", "a8", "q9", "a9"]


def test_persistence_save_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "conv.json"
    conv = Conversation(system_prompt="You are Jarvis.", path=path)
    conv.add_user("Mon nom est Noah")
    conv.add_assistant("Enchanté Noah !")

    # Vérifie que le fichier existe et est lisible
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["messages"]) == 2

    # Nouvelle instance qui recharge depuis le fichier
    conv2 = Conversation(system_prompt="You are Jarvis.", path=path)
    msgs = conv2.messages()
    assert len(msgs) == 2
    assert msgs[0].content == "Mon nom est Noah"
    assert msgs[1].content == "Enchanté Noah !"


def test_reset_clears_memory_and_disk(tmp_path: Path) -> None:
    path = tmp_path / "conv.json"
    conv = Conversation(system_prompt="sys", path=path)
    conv.add_user("Hello")
    conv.add_assistant("Hi")
    assert path.exists()

    conv.reset()
    assert conv.messages() == []
    assert not path.exists()

    # Recréer une nouvelle conv avec le même path : doit démarrer à vide
    conv2 = Conversation(system_prompt="sys", path=path)
    assert conv2.messages() == []


def test_path_none_disables_persistence() -> None:
    conv = Conversation(system_prompt="sys", path=None)
    conv.add_user("hello")
    conv.add_assistant("hi")
    # Pas de disque → juste mémoire
    assert len(conv.messages()) == 2


def test_corrupted_file_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "conv.json"
    path.write_text("not-valid-json{{{", encoding="utf-8")

    conv = Conversation(system_prompt="sys", path=path)
    # Pas de crash, juste un historique vide
    assert conv.messages() == []


def test_turn_count_returns_user_turns(tmp_path: Path) -> None:
    conv = Conversation(system_prompt="sys", path=tmp_path / "c.json")
    assert conv.turn_count() == 0
    conv.add_user("q1")
    conv.add_assistant("a1")
    conv.add_user("q2")
    assert conv.turn_count() == 2


def test_default_window_value() -> None:
    conv = Conversation(system_prompt="sys", path=None)
    assert conv.window == DEFAULT_HISTORY_WINDOW


def test_message_to_dict_roundtrip() -> None:
    m = Message.now("user", "Test")
    d = m.to_dict()
    m2 = Message.from_dict(d)
    assert m2.role == m.role
    assert m2.content == m.content
    assert m2.timestamp == m.timestamp


def test_reset_idempotent_when_no_file(tmp_path: Path) -> None:
    path = tmp_path / "doesnt-exist.json"
    conv = Conversation(system_prompt="sys", path=path)
    # Pas de fichier → reset ne doit pas crasher
    conv.reset()
    assert conv.messages() == []


@pytest.mark.parametrize("invalid", [b"\x00\x01\x02", b"random binary"])
def test_corrupted_binary_file_is_ignored(tmp_path: Path, invalid: bytes) -> None:
    path = tmp_path / "binary.json"
    path.write_bytes(invalid)
    conv = Conversation(system_prompt="sys", path=path)
    assert conv.messages() == []
