"""Module voice : TTS local (Sprint Voice MVP).

Au Sprint Voice MVP, ne contient que la sortie TTS (faire parler Jarvis).
Les futurs sprints ajouteront STT (Whisper), wake word (openWakeWord) et le
pipeline audio bas-niveau (Pipecat ou Rust).

Backends supportés :
- `chatterbox` : Resemble AI, voice cloning, GPU recommandé (~500 MB)
- `piper` : Rhasspy, CPU, voix FR neutre (~50 MB) — fallback
- `null` : pas d'audio, juste retourne le texte (utile pour tests)

Usage :
    python -m orchestrator.voice.speak "Bonjour Noah"
    python -m orchestrator.voice.speak "Test" --backend piper
    python -m orchestrator.voice.speak "Test" --save out.wav
"""

from orchestrator.voice.tts import (
    ChatterboxBackend,
    NullBackend,
    PiperBackend,
    SynthesisResult,
    TtsBackend,
    build_backend,
)

__all__ = [
    "ChatterboxBackend",
    "NullBackend",
    "PiperBackend",
    "SynthesisResult",
    "TtsBackend",
    "build_backend",
]
