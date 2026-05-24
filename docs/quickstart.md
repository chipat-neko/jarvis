# Quickstart — chat Jarvis 100% local

> 5 minutes pour avoir Jarvis qui répond en texte. **Aucune clé API**, **aucun appel cloud**. Deux backends au choix : **Ollama** (HTTP) ou **HuggingFace transformers** (in-process).

## 1. Pré-requis

- Python 3.11
- Selon le backend choisi :
  - **Ollama** (recommandé pour démarrer) : déjà installé, au moins `gpt-oss:120b` pulled (Noah a 65 GB dans `D:\model_ollama`)
  - **HuggingFace** : `torch`, `transformers`, `accelerate` (et `bitsandbytes` si tu veux quantization 4-bit). **Déjà installés** sur ton PC.
- Repo installé en editable :

  ```powershell
  cd d:\assistant_ai\jarvis
  py -3.11 -m pip install -e services\jarvis-orchestrator -e services\jarvis-llm
  ```

## 2. Lancer le chat

### Backend Ollama (défaut)

```powershell
py -3.11 -m orchestrator.chat
# → gpt-oss:120b via Ollama HTTP
```

Changer le modèle Ollama :

```powershell
py -3.11 -m orchestrator.chat --ollama-model qwen2.5:14b-instruct-q4_K_M
```

### Backend HuggingFace

Utilise les modèles déjà téléchargés dans `D:\.cache\huggingface\hub` (HF_HOME).

```powershell
py -3.11 -m orchestrator.chat --backend hf
# → Qwen/Qwen2.5-Coder-7B-Instruct par défaut (15 GB FP16, tient en VRAM RTX 5070 Ti)
```

Choisir un modèle HF spécifique parmi ceux téléchargés :

```powershell
# Petit et rapide
py -3.11 -m orchestrator.chat --backend hf --hf-model Qwen/Qwen2.5-Coder-3B-Instruct

# Compact mais correct
py -3.11 -m orchestrator.chat --backend hf --hf-model microsoft/phi-2

# Gros modèle code (15 GB, défaut)
py -3.11 -m orchestrator.chat --backend hf --hf-model Qwen/Qwen2.5-Coder-7B-Instruct

# Quantization 4-bit (bitsandbytes) pour faire tenir un gros modèle en VRAM
py -3.11 -m orchestrator.chat --backend hf --hf-model Qwen/Qwen2.5-Coder-7B-Instruct --quantize-4bit
```

**Note** : au premier appel HF, le modèle se charge en mémoire (30s à 2min selon taille). Les appels suivants sont rapides.

### Mode gRPC (architecture cible des microservices)

Terminal 1 :

```powershell
py -3.11 -m jarvis_llm.server                                       # Ollama
py -3.11 -m jarvis_llm.server --backend hf                          # HF
py -3.11 -m jarvis_llm.server --backend hf --quantize-4bit
```

Terminal 2 :

```powershell
py -3.11 -m orchestrator.chat --via-grpc
```

## 3. Modèles disponibles sur ton PC (détectés au 2026-05-24)

**Via Ollama** :
| Modèle | Taille | Note |
|---|---|---|
| `gpt-oss:120b` | 65 GB | Le plus capable. MoE, offload partiel sur 16 GB VRAM (lent mais marche) |

**Via HuggingFace** (`D:\.cache\huggingface\hub`) :
| Modèle | Taille FP16 | Instruct | Notes |
|---|---|---|---|
| `Qwen/Qwen2.5-Coder-7B-Instruct` | 15.2 GB | ✅ | **Défaut HF**, tient en VRAM 16 GB en BF16 |
| `Qwen/Qwen2.5-Coder-3B-Instruct` | 6.2 GB | ✅ | Excellent compromis vitesse/qualité |
| `microsoft/phi-2` | 5.6 GB | ✅ | Plus petit, plus rapide |
| `Qwen/Qwen2.5-Coder-1.5B` | 3.1 GB | ❌ (base) | Trop léger pour chat |
| `Qwen/Qwen2.5-Coder-0.5B` | 1.0 GB | ❌ (base) | Très léger |
| `deepseek-ai/DeepSeek-Coder-6.7b-base` | 13.5 GB | ❌ (base) | Non-instruct, peu adapté chat |

Ajouter un nouveau modèle HF : juste `git clone` ou utiliser `huggingface-cli download <model-id>` — il sera détecté automatiquement.

## 4. Fixer ton modèle par défaut

Via env var (utile pour ton profil PowerShell) :

```powershell
$env:JARVIS_LLM_MODEL = "qwen2.5:14b-instruct-q4_K_M"   # défaut backend ollama
$env:JARVIS_HF_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"  # défaut backend hf
```

## 5. Classification d'intent (observability)

À chaque tour, Jarvis classifie ta requête en `SIMPLE` / `CONVERSATIONAL` / `COMPLEX` / `CODE` / `TOOL_USE` (regex mots-clé FR/EN). Pour l'instant tous les intents tapent le même modèle, mais l'intent s'affiche en stderr :

```
Jarvis> ...
  ↳ model=Qwen/Qwen2.5-Coder-7B-Instruct intent=code
```

À terme on pourra router vers des modèles différents selon l'intent (petit modèle rapide pour conversation, gros pour code).

## 6. Limites connues

- **Pas d'historique conversation** — chaque tour indépendant.
- **Pas de streaming** — réponse d'un coup.
- **Pas de tool use réel** — TOOL_USE classé mais sans capacité d'agir (S5+).
- **HF charge le modèle à chaque démarrage** — pas de persistance entre runs. Le mode `--via-grpc` permet de garder le modèle chargé via le service jarvis-llm.

## 7. Troubleshooting

| Problème | Solution |
|---|---|
| `httpx.ConnectError` (Ollama) | Ollama ne tourne pas. Lance l'app Ollama. |
| `model not found` (Ollama) | `ollama pull <model>` ou choisis-en un dispo (`ollama list`). |
| `OutOfMemoryError` (HF) | Modèle trop gros. Active `--quantize-4bit` ou prends un plus petit. |
| `ModuleNotFoundError: torch` | Pour le backend HF. `py -3.11 -m pip install torch transformers accelerate` |
| HF lent au démarrage | Normal au 1er load (30s à 2min). Utilise `--via-grpc` pour garder le modèle chaud. |
| `Some parameters are on the meta device` | Accelerate a offload sur CPU. Normal. Active `--quantize-4bit` pour tout mettre en VRAM. |
