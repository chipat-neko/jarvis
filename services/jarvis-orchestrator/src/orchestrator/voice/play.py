"""Helpers de lecture audio (sounddevice + soundfile, lazy import).

Sépare la sortie audio du choix de backend TTS pour qu'on puisse tester un
backend sans lecteur (`--save`) ou lire un WAV sans synthèse.
"""

from __future__ import annotations

from pathlib import Path


def save_wav(wav_bytes: bytes, out_path: str | Path) -> Path:
    """Sauvegarde un buffer WAV sur disque. Crée le dossier parent si besoin."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(wav_bytes)
    return p


def play_wav(wav_bytes: bytes, *, blocking: bool = True) -> None:
    """Joue un WAV via sounddevice. Bloque jusqu'à la fin par défaut."""
    try:
        import io  # noqa: PLC0415

        import sounddevice as sd  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "sounddevice/soundfile pas installé. Lance : pip install sounddevice soundfile"
        ) from exc
    data, sr = sf.read(io.BytesIO(wav_bytes), dtype="int16")
    sd.play(data, samplerate=sr)
    if blocking:
        sd.wait()
