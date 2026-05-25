"""Tests du module orchestrator.voice (TTS pluggable + lecture audio).

Volontairement mockés : on ne charge PAS les vrais modèles Chatterbox/Piper
(trop lourds pour la CI). On valide la mécanique : factory, fallback gracieux,
roundtrip WAV, save/play.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from orchestrator.voice import (
    ChatterboxBackend,
    NullBackend,
    PiperBackend,
    SynthesisResult,
    build_backend,
)
from orchestrator.voice.play import save_wav
from orchestrator.voice.speak import main as speak_main
from orchestrator.voice.tts import _wav_duration

# ---------------------------------------------------------------------------
# NullBackend (déterministe, sert de test ground-truth)
# ---------------------------------------------------------------------------


def test_null_backend_returns_valid_wav() -> None:
    backend = NullBackend()
    result = backend.synthesize("ignored")
    assert isinstance(result, SynthesisResult)
    assert result.backend == "null"
    assert result.sample_rate == 24_000
    assert 0.99 <= result.duration_sec <= 1.01  # 1 s pile

    # WAV parsable
    with wave.open(io.BytesIO(result.wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24_000
        assert wf.getnframes() == 24_000


def test_null_backend_custom_sample_rate() -> None:
    backend = NullBackend(sample_rate=16_000)
    result = backend.synthesize("ignored")
    assert result.sample_rate == 16_000


def test_null_backend_ignores_voice_sample(tmp_path: Path) -> None:
    """NullBackend accepte (et ignore) voice_sample sans erreur."""
    backend = NullBackend()
    fake = tmp_path / "ne-sert-a-rien.wav"
    fake.write_bytes(b"")
    # Pas d'exception
    backend.synthesize("hello", voice_sample=fake)


# ---------------------------------------------------------------------------
# Factory build_backend
# ---------------------------------------------------------------------------


def test_build_backend_null() -> None:
    backend = build_backend("null")
    assert isinstance(backend, NullBackend)


def test_build_backend_piper() -> None:
    backend = build_backend("piper")
    assert isinstance(backend, PiperBackend)


def test_build_backend_chatterbox() -> None:
    backend = build_backend("chatterbox")
    assert isinstance(backend, ChatterboxBackend)


def test_build_backend_unknown_raises() -> None:
    with pytest.raises(ValueError, match="backend TTS inconnu"):
        build_backend("totalement-bidon")


# ---------------------------------------------------------------------------
# PiperBackend (lazy, sans modèle)
# ---------------------------------------------------------------------------


def test_piper_backend_missing_lib_raises(monkeypatch) -> None:
    """Sans `piper`, on doit lever RuntimeError lisible."""
    import sys

    monkeypatch.setitem(sys.modules, "piper", None)
    backend = PiperBackend(model_path=Path("/inexistant.onnx"))
    with pytest.raises(RuntimeError, match=r"piper-tts pas installé|introuvable"):
        backend.synthesize("test")


# ---------------------------------------------------------------------------
# ChatterboxBackend (lazy, sans modèle)
# ---------------------------------------------------------------------------


def test_chatterbox_backend_voice_sample_missing_raises(monkeypatch) -> None:
    """voice_sample inexistant → RuntimeError. On stubs le model pour pas le charger."""
    backend = ChatterboxBackend()
    # Stub _ensure_loaded pour bypass le chargement
    backend._ensure_loaded = lambda: None  # type: ignore[method-assign]
    backend._model = object()  # pas None
    with pytest.raises(RuntimeError, match="voice_sample introuvable"):
        backend.synthesize("test", voice_sample=Path("/n-existe-pas.wav"))


def test_chatterbox_missing_lib_raises(monkeypatch) -> None:
    """Sans le module `chatterbox`, on lève une RuntimeError lisible."""
    import sys

    monkeypatch.setitem(sys.modules, "chatterbox", None)
    monkeypatch.setitem(sys.modules, "chatterbox.tts", None)
    backend = ChatterboxBackend()
    with pytest.raises(RuntimeError, match="chatterbox-tts pas installé"):
        backend.synthesize("test")


# ---------------------------------------------------------------------------
# save_wav (play.py)
# ---------------------------------------------------------------------------


def test_save_wav_creates_file(tmp_path: Path) -> None:
    backend = NullBackend()
    result = backend.synthesize("ignored")
    out = tmp_path / "subdir" / "out.wav"
    saved = save_wav(result.wav_bytes, out)
    assert saved == out
    assert saved.exists()
    assert saved.read_bytes() == result.wav_bytes


def test_save_wav_creates_missing_parent(tmp_path: Path) -> None:
    backend = NullBackend()
    result = backend.synthesize("ignored")
    out = tmp_path / "deep" / "nested" / "path" / "out.wav"
    save_wav(result.wav_bytes, out)
    assert out.exists()


# ---------------------------------------------------------------------------
# _wav_duration helper
# ---------------------------------------------------------------------------


def test_wav_duration_handles_empty() -> None:
    assert _wav_duration(b"", 24_000) == 0.0
    assert _wav_duration(b"x" * 30, 24_000) == 0.0  # < 44 bytes (pas de header complet)


def test_wav_duration_matches_null_backend() -> None:
    """La durée calculée doit correspondre au WAV généré par NullBackend (1s)."""
    backend = NullBackend(sample_rate=16_000)
    result = backend.synthesize("x")
    assert 0.95 <= _wav_duration(result.wav_bytes, 16_000) <= 1.05


# ---------------------------------------------------------------------------
# CLI speak (mode --save avec backend null, sans audio device)
# ---------------------------------------------------------------------------


def test_cli_speak_save_with_null_backend(tmp_path: Path) -> None:
    out = tmp_path / "spoken.wav"
    rc = speak_main(["Bonjour test", "--backend", "null", "--save", str(out)])
    assert rc == 0
    assert out.exists()
    # WAV parsable
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1


def test_cli_speak_unknown_backend_returns_error(tmp_path: Path) -> None:
    # argparse va rejeter à la phase de parsing
    with pytest.raises(SystemExit):
        speak_main(["test", "--backend", "totalement-bidon"])
