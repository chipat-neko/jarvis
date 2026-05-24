# Quickstart — chat Jarvis 100% local

> Objectif : 5 minutes pour avoir Jarvis qui répond en texte. **Aucune clé API**, **aucun appel cloud**, tout tourne sur ton PC via Ollama.

## 1. Pré-requis

- Python 3.11 disponible
- Ollama installé (tu l'as déjà, vérifié `ollama list`)
- Au moins un modèle pulled. Par défaut on utilise **`gpt-oss:120b`** (le plus capable que tu aies déjà téléchargé, ~65 GB, MoE)
- Le repo cloné dans `d:\assistant_ai\jarvis` et les services installés :

  ```powershell
  cd d:\assistant_ai\jarvis
  py -3.11 -m pip install -e services\jarvis-orchestrator -e services\jarvis-llm
  ```

## 2. Vérifier qu'Ollama tourne

```powershell
ollama list
# Doit afficher au moins gpt-oss:120b
```

Si Ollama n'est pas démarré, lance-le (sous Windows il tourne en service ou via l'app).

## 3. Lancer le chat

### Mode in-process (le plus simple — recommandé pour démarrer)

```powershell
py -3.11 -m orchestrator.chat
```

→ ouvre un REPL :

```
┌─────────────────────────────────────────────────────────┐
│  Jarvis MVP — chat texte (100% local)                   │
│  mode  : in-process                                     │
│  model : gpt-oss:120b                                   │
│  /quit pour sortir, /model pour voir le modèle          │
└─────────────────────────────────────────────────────────┘

Vous> Bonjour, qui es-tu ?
Jarvis> Je suis Jarvis, ton assistant personnel local...
```

### Changer de modèle

Soit en flag :

```powershell
py -3.11 -m orchestrator.chat --model qwen2.5:14b-instruct-q4_K_M
```

Soit via env var (utile pour fixer ton choix dans ton profil) :

```powershell
$env:JARVIS_LLM_MODEL = "qwen2.5:14b-instruct-q4_K_M"
py -3.11 -m orchestrator.chat
```

### Mode gRPC (architecture cible des microservices)

Dans un terminal :

```powershell
py -3.11 -m jarvis_llm.server
# log : jarvis-llm listening on 127.0.0.1:50052
```

Dans un autre :

```powershell
py -3.11 -m orchestrator.chat --via-grpc
```

## 4. Classification d'intent (observability)

À chaque tour, Jarvis classifie ta requête en `SIMPLE` / `CONVERSATIONAL` / `COMPLEX` / `CODE` / `TOOL_USE` (regex mots-clé FR/EN). Pour l'instant tous les intents tapent le même modèle, mais l'intent s'affiche en stderr à chaque réponse :

```
Jarvis> ...
  ↳ model=gpt-oss:120b intent=code
```

À terme (S2+) on pourra router vers des modèles différents selon l'intent (petit modèle rapide pour conversation, gros pour code).

## 5. Limites connues (à améliorer)

- **Pas d'historique conversation** dans ce MVP — chaque tour est indépendant.
- **Pas de streaming** — la réponse arrive d'un coup. Streaming arrive avec le pipeline voice (S3-S4).
- **Pas de tool use réel** — quand tu demandes "ouvre Spotify", il classera TOOL_USE mais sans capacité d'agir. C'est S5+ (MCP).
- **gpt-oss:120b est lent sur ton RTX 5070 Ti 16GB** (offload partiel VRAM/RAM). Si trop lent, change pour un modèle qui tient en VRAM (`qwen2.5:14b-instruct-q4_K_M` ~9 GB → ~50-80 tok/s).
- **Intent classifier basique** — regex mots-clé. Améliorable avec embeddings.

## 6. Troubleshooting

| Problème | Solution |
|---|---|
| `httpx.ConnectError` au démarrage | Ollama ne tourne pas. Lance l'app Ollama ou `ollama serve`. |
| `model "gpt-oss:120b" not found` | `ollama pull gpt-oss:120b` ou choisis-en un autre via `--model`. |
| Réponse super lente | Modèle trop gros pour la VRAM. Bascule sur `qwen2.5:14b-instruct-q4_K_M` ou plus petit. |
| `ModuleNotFoundError: jarvis_llm` | Pas installé en editable. `py -3.11 -m pip install -e services\jarvis-llm` |
| `pytest` warning asyncio | `py -3.11 -m pip install pytest-asyncio` |
