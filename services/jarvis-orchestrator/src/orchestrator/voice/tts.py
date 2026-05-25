"""TTS backends pluggables.

Interface commune `TtsBackend` (Protocol) + 3 implémentations :

- `NullBackend` : ne génère rien, retourne un WAV vide. Pour les tests CI
  qui ne peuvent pas (ne doivent pas) charger un modèle de 500 MB.
- `PiperBackend` : Rhasspy Piper en CPU. Voix FR neutre, latence < 200 ms,
  ~50 MB de modèle. Le plus simple à brancher. Pas de voice cloning.
- `ChatterboxBackend` : Resemble AI Chatterbox sur GPU. Qualité top, voice
  cloning depuis un sample audio. ~500 MB de modèle.

Les backends sont **lazy** : aucun import lourd (torch, chatterbox) au top
du module → on peut importer `tts.py` sans payer le coût de chargement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_SAMPLE_RATE = 24_000


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Résultat d'une synthèse : audio PCM 16-bit mono + sample rate."""

    wav_bytes: bytes  # WAV complet (header + data), prêt à écrire sur disque ou jouer
    sample_rate: int = DEFAULT_SAMPLE_RATE
    duration_sec: float = 0.0
    backend: str = "unknown"


class TtsBackend(Protocol):
    """Interface des backends TTS."""

    name: str

    def synthesize(self, text: str, *, voice_sample: str | Path | None = None) -> SynthesisResult:
        """Génère un WAV à partir d'un texte.

        Args:
            text: texte à parler (en français par défaut).
            voice_sample: chemin d'un clip audio pour le voice cloning.
                Ignoré par les backends qui ne supportent pas le cloning.
        """
        ...


# ---------------------------------------------------------------------------
# NullBackend (tests, fallback)
# ---------------------------------------------------------------------------


class NullBackend:
    """Backend factice : retourne un WAV silencieux d'1 seconde."""

    name = "null"

    def __init__(self, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    def synthesize(
        self,
        text: str,
        *,
        voice_sample: str | Path | None = None,
    ) -> SynthesisResult:
        import wave  # noqa: PLC0415 — lazy
        from io import BytesIO  # noqa: PLC0415

        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"\x00\x00" * self.sample_rate)  # 1s de silence
        return SynthesisResult(
            wav_bytes=buf.getvalue(),
            sample_rate=self.sample_rate,
            duration_sec=1.0,
            backend=self.name,
        )


# ---------------------------------------------------------------------------
# PiperBackend (CPU, FR, simple)
# ---------------------------------------------------------------------------


class PiperBackend:
    """Wrapper Piper TTS (CPU). Voix FR neutre.

    Lazy import : le module `piper` n'est chargé qu'au premier synthesize().
    Voice cloning non supporté (l'argument est ignoré).
    """

    name = "piper"

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        sample_rate: int = 22_050,
    ) -> None:
        # Modèle par défaut : fr_FR-tom-medium (~63 MB).
        # Si pas fourni, on assume qu'il est dans models/piper/.
        self.model_path = (
            Path(model_path) if model_path else Path("models/piper/fr_FR-tom-medium.onnx")
        )
        self.sample_rate = sample_rate
        self._voice = None

    def _ensure_loaded(self) -> None:
        if self._voice is not None:
            return
        try:
            from piper import PiperVoice  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("piper-tts pas installé. Lance : pip install piper-tts") from exc
        if not self.model_path.exists():
            raise RuntimeError(
                f"modèle Piper introuvable : {self.model_path}. "
                "Télécharge fr_FR-tom-medium.onnx depuis "
                "https://github.com/rhasspy/piper/releases"
            )
        self._voice = PiperVoice.load(str(self.model_path))

    def synthesize(
        self,
        text: str,
        *,
        voice_sample: str | Path | None = None,
    ) -> SynthesisResult:
        self._ensure_loaded()
        import io  # noqa: PLC0415
        import wave  # noqa: PLC0415

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._voice.synthesize(text, wf)
        wav_bytes = buf.getvalue()
        duration = _wav_duration(wav_bytes, self.sample_rate)
        return SynthesisResult(
            wav_bytes=wav_bytes,
            sample_rate=self.sample_rate,
            duration_sec=duration,
            backend=self.name,
        )


# ---------------------------------------------------------------------------
# ChatterboxBackend (GPU, voice cloning)
# ---------------------------------------------------------------------------


class ChatterboxBackend:
    """Wrapper Chatterbox (Resemble AI) avec voice cloning.

    Le modèle est lourd (~500 MB) et nécessite torch + GPU recommandé. Lazy
    import au premier synthesize().
    """

    name = "chatterbox"

    def __init__(self, *, device: str = "cuda", sample_rate: int = 24_000) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from chatterbox.tts import ChatterboxTTS  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "chatterbox-tts pas installé. Lance : pip install chatterbox-tts"
            ) from exc
        self._model = ChatterboxTTS.from_pretrained(device=self.device)

    def synthesize(
        self,
        text: str,
        *,
        voice_sample: str | Path | None = None,
    ) -> SynthesisResult:
        self._ensure_loaded()
        kwargs: dict = {}
        if voice_sample is not None:
            sample_path = Path(voice_sample)
            if not sample_path.exists():
                raise RuntimeError(f"voice_sample introuvable : {sample_path}")
            kwargs["audio_prompt_path"] = str(sample_path)
        wav_tensor = self._model.generate(text, **kwargs)
        wav_bytes = _tensor_to_wav_bytes(wav_tensor, sample_rate=self.sample_rate)
        duration = _wav_duration(wav_bytes, self.sample_rate)
        return SynthesisResult(
            wav_bytes=wav_bytes,
            sample_rate=self.sample_rate,
            duration_sec=duration,
            backend=self.name,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_backend(
    kind: str,
    *,
    chatterbox_device: str = "cuda",
    piper_model: str | Path | None = None,
) -> TtsBackend:
    """Construit le backend demandé. Lève ValueError si kind inconnu.

    `kind` : "null" | "piper" | "chatterbox".
    """
    if kind == "null":
        return NullBackend()
    if kind == "piper":
        return PiperBackend(model_path=piper_model)
    if kind == "chatterbox":
        return ChatterboxBackend(device=chatterbox_device)
    raise ValueError(f"backend TTS inconnu : '{kind}' (choix: null, piper, chatterbox)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wav_duration(wav_bytes: bytes, sample_rate: int) -> float:
    """Estime la durée d'un WAV à partir de sa taille."""
    if len(wav_bytes) < 44:
        return 0.0
    data_len = max(0, len(wav_bytes) - 44)
    samples = data_len // 2  # 16-bit mono
    return samples / max(1, sample_rate)


def _tensor_to_wav_bytes(tensor, *, sample_rate: int) -> bytes:
    """Convertit un tensor PyTorch (1D ou 2D float [-1, 1]) en WAV PCM 16-bit mono."""
    import io  # noqa: PLC0415
    import wave  # noqa: PLC0415

    # Tensor → numpy float [-1, 1]
    arr = tensor.detach().cpu().numpy() if hasattr(tensor, "detach") else tensor
    if arr.ndim == 2:
        # (channels, samples) ou (batch, samples) → on prend le 1er canal
        arr = arr[0]
    # Clamp + convert int16
    arr = (arr.clip(-1.0, 1.0) * 32767).astype("int16")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(arr.tobytes())
    return buf.getvalue()
