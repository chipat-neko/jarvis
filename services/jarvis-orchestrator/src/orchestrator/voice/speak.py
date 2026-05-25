"""CLI : `python -m orchestrator.voice.speak "Bonjour Noah"`.

Synthétise un texte avec le backend choisi (Chatterbox par défaut), puis joue
l'audio ou le sauvegarde sur disque selon les options.

Examples:
    python -m orchestrator.voice.speak "Bonjour Noah"
    python -m orchestrator.voice.speak "Test" --backend piper
    python -m orchestrator.voice.speak "Test" --save .local/out.wav
    python -m orchestrator.voice.speak "Test" --voice-sample .local/jarvis_vf.wav
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from orchestrator.voice.play import play_wav, save_wav
from orchestrator.voice.tts import build_backend

DEFAULT_BACKEND = "chatterbox"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fait parler Jarvis avec un backend TTS local (Chatterbox/Piper/null).",
    )
    parser.add_argument("text", help="texte à synthétiser")
    parser.add_argument(
        "--backend",
        choices=["chatterbox", "piper", "null"],
        default=DEFAULT_BACKEND,
        help=f"backend TTS (défaut {DEFAULT_BACKEND})",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="sauvegarde le WAV sur ce chemin au lieu de le jouer",
    )
    parser.add_argument(
        "--voice-sample",
        type=Path,
        default=None,
        help="clip audio de référence pour le voice cloning (Chatterbox uniquement)",
    )
    parser.add_argument(
        "--chatterbox-device",
        default="cuda",
        help="device pour Chatterbox : 'cuda' ou 'cpu' (défaut cuda)",
    )
    parser.add_argument(
        "--piper-model",
        type=Path,
        default=None,
        help="chemin du modèle Piper .onnx (défaut models/piper/fr_FR-tom-medium.onnx)",
    )
    args = parser.parse_args(argv)

    try:
        backend = build_backend(
            args.backend,
            chatterbox_device=args.chatterbox_device,
            piper_model=args.piper_model,
        )
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    print(f"[speak] synthèse via {backend.name}…", file=sys.stderr)
    try:
        result = backend.synthesize(args.text, voice_sample=args.voice_sample)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3

    print(
        f"[speak] {result.duration_sec:.2f}s de WAV "
        f"({len(result.wav_bytes)} bytes @ {result.sample_rate} Hz)",
        file=sys.stderr,
    )

    if args.save is not None:
        saved = save_wav(result.wav_bytes, args.save)
        print(f"[speak] sauvegardé → {saved}", file=sys.stderr)
        return 0

    try:
        play_wav(result.wav_bytes)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
