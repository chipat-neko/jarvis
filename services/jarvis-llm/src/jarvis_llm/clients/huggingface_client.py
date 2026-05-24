"""Wrapper HuggingFace `transformers` pour Jarvis (LLM local, alternative à Ollama).

Permet d'utiliser n'importe quel modèle HF déjà téléchargé dans `HF_HOME`
(défaut `~/.cache/huggingface` ou `D:\\.cache\\huggingface` chez Noah).

Le modèle est chargé en lazy au premier appel pour ne pas pénaliser l'import.
Génération sync (`model.generate`) wrappée en async via `asyncio.to_thread`.

Modèle par défaut : `Qwen/Qwen2.5-Coder-7B-Instruct` (15 GB FP16, tient en VRAM
RTX 5070 Ti 16GB). Override via `$JARVIS_HF_MODEL`.

Pour les modèles trop gros, activer la quantization 4-bit via `quantize_4bit=True`
(nécessite `bitsandbytes`, déjà installé).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

DEFAULT_HF_MODEL = os.environ.get("JARVIS_HF_MODEL", "Qwen/Qwen2.5-Coder-7B-Instruct")


@dataclass(frozen=True, slots=True)
class HuggingFaceCompletion:
    """Résultat d'une complétion HuggingFace."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class HuggingFaceClient:
    """Client local pour les modèles HuggingFace via `transformers`.

    Args:
        model_id: identifiant HF (ex: "Qwen/Qwen2.5-Coder-7B-Instruct").
            Cherche d'abord dans le cache HF, télécharge sinon.
        device: "auto" (recommandé), "cuda", "cpu". `device_map="auto"` laisse
            `accelerate` répartir entre VRAM/RAM/disque selon dispo.
        dtype: "auto" (bf16 sur GPU récents, fp32 sur CPU), "bfloat16", "float16", "float32".
        quantize_4bit: si True, charge en 4-bit via bitsandbytes (~4x moins de VRAM,
            qualité ~95% de FP16). Utile pour les modèles > VRAM dispo.
    """

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_HF_MODEL,
        device: str = "auto",
        dtype: str = "auto",
        quantize_4bit: bool = False,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.quantize_4bit = quantize_4bit
        # Lazy : on charge le modèle au 1er appel pour pas payer le coût à l'import.
        self._tokenizer = None
        self._model = None
        self._load_lock: asyncio.Lock | None = None

    @property
    def model(self) -> str:
        """Alias pour rester compatible avec l'interface OllamaClient (qui expose .model)."""
        return self.model_id

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Évite le double-load en cas d'appels concurrents.
        if self._load_lock is None:
            self._load_lock = asyncio.Lock()
        async with self._load_lock:
            if self._model is not None:
                return
            await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> None:
        # Imports lourds — laissés ici pour ne pas peser sur l'import du module.
        import torch  # noqa: PLC0415
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

        load_kwargs: dict = {}

        if self.quantize_4bit:
            from transformers import BitsAndBytesConfig  # noqa: PLC0415

            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        elif self.dtype != "auto":
            load_kwargs["dtype"] = getattr(torch, self.dtype)
        else:
            # bf16 par défaut si GPU compatible, sinon float32
            load_kwargs["dtype"] = (
                torch.bfloat16
                if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                else torch.float32
            )

        if self.device == "auto":
            load_kwargs["device_map"] = "auto"
        elif self.device != "cpu":
            load_kwargs["device_map"] = self.device

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, **load_kwargs)

        # eos_token_id manquant sur certains tokenizers
        if self._tokenizer.pad_token_id is None:
            self._tokenizer.pad_token_id = self._tokenizer.eos_token_id

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> HuggingFaceCompletion:
        """Génère une complétion mono-tour (compat MVP initial).

        Pour le multi-tour avec historique, préférer `chat(messages, ...)`.
        """
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, max_tokens=max_tokens)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> HuggingFaceCompletion:
        """Génère une complétion multi-tour depuis une liste de messages.

        Args:
            messages: liste au format OpenAI/Ollama
                ([{"role": "system|user|assistant", "content": "..."}, ...]).
            max_tokens: limite de tokens en sortie (mappé sur `max_new_tokens`).
        """
        await self._ensure_loaded()
        assert self._tokenizer is not None
        assert self._model is not None
        return await asyncio.to_thread(self._chat_sync, messages, max_tokens=max_tokens)

    def _chat_sync(
        self, messages: list[dict[str, str]], *, max_tokens: int
    ) -> HuggingFaceCompletion:
        import torch  # noqa: PLC0415

        assert self._tokenizer is not None
        assert self._model is not None

        # `apply_chat_template` renvoie un BatchEncoding (dict-like) en transformers 5.x.
        # Tous les modèles `*-Instruct` modernes (Qwen, Llama 3, Phi, ...) ont un template.
        inputs = self._tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"]
        prompt_tokens = input_ids.shape[-1]

        with torch.inference_mode():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        # outputs[0] = prompt + completion. On ne garde que la completion.
        completion_ids = outputs[0][prompt_tokens:]
        completion_text = self._tokenizer.decode(completion_ids, skip_special_tokens=True)

        return HuggingFaceCompletion(
            text=completion_text.strip(),
            model=self.model_id,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_ids.shape[-1]),
        )
