# Quickstart — chat Jarvis en local

> Objectif : 5 minutes pour avoir Jarvis qui répond en texte. Pas de voice, pas de Computer Use — juste un REPL qui parle à Sonnet 4.6 (et/ou Qwen 14B local si tu as Ollama).

## 1. Pré-requis

- Python 3.11 disponible (le repo est testé sur 3.11)
- Le repo cloné dans `d:\assistant_ai\jarvis` et les services Python installés en editable :

  ```powershell
  cd d:\assistant_ai\jarvis
  py -3.11 -m pip install -e services\jarvis-orchestrator -e services\jarvis-llm
  ```

- Une clé API Anthropic (https://console.anthropic.com/). Côté gratuit/payant — tu auras besoin d'au moins quelques crédits pour tester.

## 2. Stocker la clé API dans le keyring Windows

Une fois pour toutes :

```powershell
py -3.11 -File scripts\setup_keyring.ps1
# (te demande la clé puis la stocke dans Windows Credential Manager
#  sous service="jarvis", username="anthropic_api_key")
```

Ou en une ligne :

```powershell
py -3.11 -c "import keyring; keyring.set_password('jarvis', 'anthropic_api_key', 'sk-ant-VOTRE-CLE')"
```

Vérification :

```powershell
py -3.11 -c "from jarvis_llm.secrets import get_anthropic_api_key; print('OK' if get_anthropic_api_key() else 'INTROUVABLE')"
```

Alternative sans keyring : variable d'env `ANTHROPIC_API_KEY` (mais le keyring est plus sûr).

## 3. (Optionnel) Ollama pour le mode local

```powershell
# Télécharge depuis https://ollama.com puis :
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama serve  # tourne en arrière-plan, déjà fait par défaut sur Win
```

Si Ollama n'est pas dispo, Jarvis fallback automatiquement sur le cloud.

## 4. Lancer le chat

### Mode in-process (le plus simple — recommandé pour démarrer)

```powershell
py -3.11 -m orchestrator.chat
```

→ ouvre un REPL :

```
┌─────────────────────────────────────────────────────────┐
│  Jarvis MVP — chat texte                                │
│  mode     : in-process                                  │
│  backends : cloud Sonnet 4.6, local Qwen 14B            │
│  /quit pour sortir, /reset pour effacer l'historique    │
└─────────────────────────────────────────────────────────┘

Vous> Bonjour, qui es-tu ?
Jarvis [cloud]> Je suis Jarvis, ton assistant personnel...
```

### Forcer le cloud

```powershell
py -3.11 -m orchestrator.chat --no-local
```

### Forcer le local

```powershell
py -3.11 -m orchestrator.chat --no-cloud
```

### Mode gRPC (architecture cible)

Dans un terminal :

```powershell
py -3.11 -m jarvis_llm.server
```

Dans un autre :

```powershell
py -3.11 -m orchestrator.chat --via-grpc
```

## 5. Comprendre le routing

À chaque tour, Jarvis :

1. Classe ta requête en intent (`SIMPLE` / `CONVERSATIONAL` / `COMPLEX` / `CODE` / `TOOL_USE`)
2. Décide local ou cloud :
   - `CODE` / `COMPLEX` / `TOOL_USE` → cloud Sonnet 4.6
   - `SIMPLE` / `CONVERSATIONAL` → local Qwen 14B (si dispo, sinon cloud)
   - prompt > ~2000 tokens estimés → cloud (Qwen perd en qualité sur long contexte)

Tu peux voir la cible utilisée affichée à chaque réponse : `Jarvis [cloud]>` ou `Jarvis [local]>`. La raison du routing s'affiche en stderr.

## 6. Limites connues (à améliorer plus tard)

- **Pas d'historique conversation** dans ce MVP — chaque tour est indépendant. La prochaine itération (S2-S3) ajoutera un context window simple.
- **Pas de streaming** — la réponse arrive d'un coup. Streaming arrive avec le pipeline voice (S3-S4).
- **Pas de tool use** — quand tu demandes "ouvre Spotify", il classera l'intent en TOOL_USE et appellera Sonnet, mais sans capacité d'agir. C'est S5+ (MCP).
- **Intent classifier basique** — regex mots-clé. Améliorable avec embeddings plus tard.

## 7. Troubleshooting

| Problème | Solution |
|---|---|
| `Aucun backend LLM disponible` | Ni clé Anthropic ni Ollama. Configure au moins l'un des deux. |
| `RuntimeError: Clé API Anthropic introuvable` | Re-stocke la clé (étape 2). |
| `httpx.ConnectError` côté Ollama | `ollama serve` ne tourne pas. Démarre-le ou lance avec `--no-local`. |
| `ModuleNotFoundError: jarvis_llm` | Pas installé en editable. Refais l'étape 1. |
| `pytest` échoue avec asyncio | `py -3.11 -m pip install pytest-asyncio` |
