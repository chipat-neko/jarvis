# Architecture Jarvis

> Détail technique de l'architecture cible. Vue d'ensemble dans [README.md](README.md).

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│            SATELLITES (ESP32-S3-BOX-3, ×2-3)                │
│             Wake Word local · Relay audio HA                 │
└─────────────────────────┬───────────────────────────────────┘
                          │ Wyoming / HA Assist (LAN)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        PC PRINCIPAL — Ryzen 7 9800X3D + RTX 5070 Ti          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  Pipecat    │→│  LangGraph    │→│  Anthropic CU /   │    │
│  │  pipeline   │  │  orchestration│  │  Local PyAutoGUI │    │
│  │  voice      │  │  (state mc)  │  │  + OmniParser    │    │
│  └──────┬──────┘  └───────┬──────┘  └──────────────────┘    │
│         │                 │                                  │
│  ┌──────▼──────┐  ┌──────▼──────────────────────────────┐   │
│  │ STT/TTS     │  │  Sonnet 4.6 (cloud, par défaut)     │   │
│  │ local CUDA  │  │  Qwen 3.5 14B (local, low-cost)     │   │
│  └─────────────┘  └─────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  Mem0 +     │  │  8 MCP        │  │  Frigate NVR     │    │
│  │  sqlite-vec │  │  servers      │  │  (Phase 2)       │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SAFETY : kill switch HW · audit log · blacklist     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST / WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Home Assistant (Pi 5, Phase 2)                  │
│         Zigbee · Matter · Caméras · Capteurs IoT             │
└─────────────────────────────────────────────────────────────┘
```

---

## Modules Python

### `jarvis.core`

Cœur orchestration. Démarre / arrête le pipeline, gère la config, expose le logger.

- `assistant.py` — entrée principale (instancie tout, démarre la boucle Pipecat)
- `config.py` — chargement YAML + override depuis env / keyring
- `logger.py` — logger structuré (loguru) + handlers fichier + console

### `jarvis.speech`

Tout l'audio I/O.

- `hotword.py` — wake word (openWakeWord)
- `recognizer.py` — STT (faster-whisper)
- `tts.py` — TTS (Chatterbox GPU, fallback Piper)

### `jarvis.nlp`

Compréhension + génération texte.

- `llm.py` — router local/cloud (Sonnet 4.6 ↔ Qwen 14B)
- `intent.py` — classification rapide d'intent (avant LLM lourd, optimisation latence)

### `jarvis.actions`

Skills/tools exposés au LLM via MCP ou function calling.

- `home_automation.py` — Home Assistant API
- `system.py` — process, OS, fichiers (avec safety wrapper)
- `calendar.py` — Google Calendar / Outlook
- `email.py` — Gmail / Outlook
- `websearch.py` — Brave Search MCP
- `music.py` — Spotify MCP
- `custom/` — sous-dossier pour skills perso ajoutés au fil du temps

### Modules à ajouter (sprints futurs)

| Module | Sprint | Rôle |
|---|---|---|
| `jarvis.memory` | S5 | Mem0 + sqlite-vec + embeddings BGE |
| `jarvis.cu` | S7 | Anthropic Computer Use + OmniParser SoM |
| `jarvis.tools.mcp` | S6 | Client MCP générique pour les 8 servers cœur |
| `jarvis.ui` | S10 | HUD + multi-screen + hotkeys |
| `jarvis.safety` | S11 | Kill switch endpoint + audit log + blacklist |
| `jarvis.integrations.ha` | S6 | Wrapper Home Assistant REST + WebSocket |
| `jarvis.orchestration.graph` | S9 | LangGraph state machine |

---

## Pipeline temps réel (Pipecat)

```
microphone audio stream
  → VAD (Silero) découpe les segments parlés
  → Wake word detection ("Hey Jarvis")
  → STT (Whisper large-v3-turbo CUDA)
  → Intent classifier rapide (jarvis.nlp.intent)
  → Decision routing :
       ├─ Local-only (intent simple)   → Qwen 14B local
       └─ Complex / agent (CU, tools)  → Sonnet 4.6 cloud
  → Tool execution (MCP servers OU Computer Use OU local action)
  → Response synthesis
  → TTS (Chatterbox GPU)
  → speaker audio output
```

Latence cible end-to-end (commande simple) : **< 1.5 s** sur RTX 5070 Ti.

---

## Stratégie LLM hybride

| Critère | Routing |
|---|---|
| Intent simple ("quelle heure", "stop musique") | Local Qwen 14B (latence < 500 ms) |
| Conversation libre / question ouverte | Sonnet 4.6 (qualité) |
| Computer Use (cliquer / taper) | Sonnet 4.6 obligatoire (pas de CU local fiable) |
| Tool calling (MCP) | Sonnet 4.6 (tool use le plus robuste du marché) |
| Génération longue / résumé doc | Sonnet 4.6 |
| Translation rapide | Local Qwen 14B |

Le router est dans `jarvis.nlp.llm.LLMRouter` (à écrire en S2).

---

## Safety / Security

Voir la card Trello "🩷 Safety / Security" (Index) pour les détails.

Couches de protection :

1. **Kill switch hardware** (Pi Pico W + bouton arcade) → coupe TOUS les services Jarvis en < 100 ms via POST `localhost:8765/kill`
2. **Audit log SQLite** : toutes les actions CU + appels MCP + intents + outputs (retention 90j)
3. **Blacklist YAML** : URLs (sites bancaires), paths système, process protégés
4. **Confirmation vocale** : delete file, send email, transfer money, install app → demande "oui" explicite
5. **Sandboxing** : code généré par LLM exécuté dans Docker container, jamais directement
6. **Secrets en keyring OS** : jamais en `.env` commit, jamais dans le code

---

## Coûts ops estimés (mensuel)

| Poste | Estimation | Note |
|---|---|---|
| Sonnet 4.6 API (avec prompt caching) | 30-50 € | Selon usage |
| LLM local (élec GPU) | ~5 € | Strix Halo / RTX 5070 Ti idle bas |
| Whisper STT local | 0 € | GPU local |
| TTS Chatterbox local | 0 € | GPU local |
| HA + add-ons | 0 € | Self-host |
| **Total** | **~40-60 €/mois** | Très soutenable |

---

## Roadmap technique

Voir [README.md#roadmap](README.md#roadmap-résumé-12-semaines) et le board Trello pour le détail sprint par sprint.
