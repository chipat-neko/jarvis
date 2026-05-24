# Jarvis

> Assistant vocal personnel style J.A.R.V.I.S — contrôle 100 % du PC, multi-écran, smart home, mémoire long terme.

Projet privé en cours de développement. Plan : MVP fonctionnel en 12 semaines.

---

## Status

**Sprint en cours : S1 — Setup environnement (foundation)**
Date de démarrage : 25 mai 2026.

Voir le suivi détaillé sur le board Trello [Jarvis](https://trello.com/b/y65Q5giL/jarvis) (privé).

---

## Stack technique

| Brique | Choix |
|---|---|
| Wake word | openWakeWord (PC) + microWakeWord (ESP32 satellites) |
| STT | faster-whisper `large-v3-turbo` (CUDA local) |
| LLM cloud | Anthropic Claude Sonnet 4.6 (orchestration complexe) |
| LLM local | Qwen 3.5 14B Q4 via Ollama (routing low-cost) |
| TTS | Chatterbox (GPU local) — fallback Piper si CPU |
| Pipeline temps réel | Pipecat |
| Orchestration états | LangGraph + LangSmith observability |
| Mémoire long terme | Mem0 + sqlite-vec + embeddings BGE-large |
| Computer Use | Anthropic CU + OmniParser (Set-of-Mark local GPU) |
| Tools / intégrations | MCP servers (filesystem, github, brave, home-assistant, spotify, gmail, notion) |
| Smart home | Home Assistant (backbone domotique) |
| Safety | Kill switch hardware Pi Pico W + audit log SQLite + blacklist scope |

---

## Hardware cible (validé sur PC de Noah)

- CPU : AMD Ryzen 7 9800X3D (8c/16t Zen 5 + 3D V-Cache)
- GPU : NVIDIA RTX 5070 Ti 16 GB GDDR7 (CUDA 13.2)
- RAM : 64 GB DDR5-5600
- SSD : 4.6 TB total
- Écrans : 3 (vertical 1440×2560 + ultrawide 3440×1440 primary + FHD 1920×1080)
- OS : Windows 11 Pro 24H2

Coûts ops estimés : ~50 €/mois (essentiellement Anthropic API, électricité GPU négligeable).

---

## Structure du repo

```
jarvis/
├── jarvis/              Package Python principal
│   ├── core/            Orchestration, config, logging
│   ├── speech/          Wake word, STT, TTS
│   ├── nlp/             LLM router, intent parsing
│   ├── actions/         Skills (home_automation, system, calendar, email, websearch, music, custom/)
│   ├── utils/           Helpers, validators
│   └── tests/           Tests unitaires + intégration
├── config/              Configuration (config.yaml versionné, secrets locaux gitignored)
├── scripts/             Scripts d'install + ops
├── requirements.txt     Dépendances Python
├── README.md            Ce fichier
├── ARCHITECTURE.md      Détail technique de l'architecture
└── .gitignore           Tout ce qui ne doit pas être commit
```

Les modules `voice/`, `llm/`, `memory/`, `cu/`, `tools/`, `ui/`, `safety/`, `integrations/` seront ajoutés au fil des sprints suivants.

---

## Setup local

> Setup détaillé à venir une fois S1 terminé. Pour l'instant la base est en place mais les modules sont vides.

### Pré-requis

- Python 3.12+
- WSL2 + Ubuntu 24.04 LTS (pour certaines dépendances Linux)
- Docker Desktop
- Ollama (https://ollama.com)
- CUDA 13.2 + driver NVIDIA récent
- Compte Anthropic Console (API key)

### Installation (work-in-progress)

```bash
git clone git@github.com:chipat-neko/jarvis.git
cd jarvis
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # Linux/WSL
pip install -r requirements.txt
ollama pull qwen2.5:14b-instruct-q4_K_M
```

### Configuration

- Copier `config/config.example.yaml` → `config/local.yaml` (gitignored) et remplir
- Stocker l'API key Anthropic dans le keyring Windows (pas dans `.env`) :
  ```python
  import keyring
  keyring.set_password("jarvis", "anthropic_api_key", "sk-ant-...")
  ```

---

## Documentation interne

- **Blueprint final** : `d:/assistant_ai/recherche/100-jarvis-final-blueprint/`
- **Roadmap 12 semaines** : `d:/assistant_ai/recherche/99-jarvis-roadmap/`
- **Comparatif hardware** : `d:/assistant_ai/recherche/hardware-comparatif-noah/`
- **100 sujets de recherche** : `d:/assistant_ai/recherche/index.html`

---

## Roadmap (résumé 12 semaines)

| Phase | Semaines | Objectif |
|---|---|---|
| Foundation | S1-S2 | Setup environnement, LLM cœur local + cloud |
| Voice IO | S3-S4 | STT/VAD, wake word, TTS, pipeline Pipecat |
| Memory + Tools | S5-S6 | Mem0 + sqlite-vec, 8 MCP servers |
| PC Control | S7-S8 | Anthropic CU + OmniParser, Open Interpreter, browser-use |
| Orchestration | S9-S10 | LangGraph state machines, multi-screen aware |
| Polish & Safety | S11-S12 | Kill switch, audit log, service Windows, monitoring |

Détail dans la card Trello correspondante.

---

## Licence

**Privé — tous droits réservés.**
Pas de redistribution, pas d'usage commercial, pas de fork public. Code perso.

---

🤖 *Projet co-piloté avec Claude (Anthropic) via Claude Code et l'API Computer Use.*
