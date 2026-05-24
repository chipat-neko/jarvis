# Jarvis

[![Python CI](https://github.com/chipat-neko/jarvis/actions/workflows/python-ci.yml/badge.svg)](https://github.com/chipat-neko/jarvis/actions/workflows/python-ci.yml)
[![Rust CI](https://github.com/chipat-neko/jarvis/actions/workflows/rust-ci.yml/badge.svg)](https://github.com/chipat-neko/jarvis/actions/workflows/rust-ci.yml)

> Assistant vocal personnel style J.A.R.V.I.S — contrôle 100 % du PC, multi-écran, smart home, mémoire long terme.

Projet privé en cours de développement. Architecture **microservices Python + Rust avec gRPC** (cf [ADR-0001](docs/adr/0001-microservices-python-rust.md)). MVP cible : mi-septembre 2026 (14-15 semaines).

---

## Status

**Sprint en cours : S1 — Setup environnement (foundation)**
Démarrage : 25 mai 2026. Suivi détaillé sur le board Trello [Jarvis](https://trello.com/b/y65Q5giL/jarvis) (privé).

---

## Stack technique

| Brique | Langage | Choix |
|---|---|---|
| Pipeline voice (wake / STT / VAD / TTS / audio I/O) | **Rust** | `jarvis-voice` — openWakeWord + faster-whisper + Silero VAD + Chatterbox + WASAPI loopback |
| LLM | Python | **100% local** : Ollama (`qwen3:14b` défaut, ~31 tok/s think=False) **ou** HuggingFace transformers (Qwen Coder, Phi-2, etc. en cache local D:) |
| Orchestration états | Python | LangGraph + LangSmith observability |
| Pipeline temps réel | Python | Pipecat (intégration côté Python, voice pipeline interne en Rust) |
| Mémoire long terme | Python | Mem0 + sqlite-vec + embeddings BGE-large |
| Computer Use | Python | OmniParser local GPU (Set-of-Mark) + pyautogui (à coder, S7-S8) |
| Tools / intégrations | Python | MCP servers (filesystem, github, brave, home-assistant, spotify, gmail, notion) |
| Smart home | externe | Home Assistant (backbone domotique) |
| UI / HUD | Python | PySide6 (Qt) + hotkeys + systray |
| Safety | Python + Rust | Kill switch HW Pi Pico W + audit log SQLite + blacklist + voice confirms |

Communication inter-services : **gRPC sur localhost** (contrats versionnés dans [`proto/`](proto/)).

---

## Hardware cible (validé sur PC de Noah)

- CPU : AMD Ryzen 7 9800X3D (8c/16t Zen 5 + 3D V-Cache)
- GPU : NVIDIA RTX 5070 Ti 16 GB GDDR7 (CUDA 13.2)
- RAM : 64 GB DDR5-5600
- SSD : 4.6 TB total
- Écrans : 3 (vertical 1440×2560 + ultrawide 3440×1440 primary + FHD 1920×1080)
- OS : Windows 11 Pro 24H2

Coûts ops estimés : **~0 €/mois** (100% local, juste l'électricité). Anthropic API retiré du stack — Jarvis tourne entièrement sur le PC de Noah.

---

## Structure du repo

```
jarvis/
├── services/                       Microservices (chacun avec son manifest)
│   ├── jarvis-orchestrator/        Python — point d'entrée principal (LangGraph + Pipecat)
│   ├── jarvis-voice/               Rust — pipeline voice temps réel (wake, STT, VAD, TTS)
│   ├── jarvis-llm/                 Python — wrapper Ollama (100% local)
│   ├── jarvis-cu/                  Python — Computer Use + OmniParser
│   ├── jarvis-tools/               Python — wrappers MCP servers
│   ├── jarvis-memory/              Python — Mem0 + sqlite-vec
│   ├── jarvis-ui/                  Python — HUD Qt + hotkeys + tray
│   └── jarvis-safety/              Python + Rust — kill switch + audit + blacklist
├── proto/                          Schemas gRPC (source of truth)
├── infra/                          Docker Compose, systemd, Prometheus, Grafana
├── docs/
│   └── adr/                        Architecture Decision Records
├── .github/workflows/              CI GitHub Actions (à venir)
├── scripts/                        Scripts dev (codegen, install, ops)
├── config/                         Config commune (config.example.yaml)
├── Cargo.toml                      Workspace Rust racine
├── pyproject.toml                  Workspace Python racine (lint/type/test transverses)
├── README.md                       Ce fichier
├── ARCHITECTURE.md                 Détails techniques
└── .gitignore
```

Chaque service Python a son `pyproject.toml` et son arbo `src/jarvis_X/` + `tests/`. Le Rust workspace contient pour l'instant uniquement `jarvis-voice` ; les autres services Rust (partie Rust de `jarvis-safety`) seront ajoutés au fil des sprints.

---

## Setup local

### Pré-requis

- Python ≥ 3.11
- Rust stable ≥ 1.95 (rustup) + Cargo
- protoc ≥ 28
- Ollama (https://ollama.com)
- CUDA 13.2 + driver NVIDIA récent
- Docker Desktop (pour Home Assistant et observability stack)
- Aucune clé API requise (100% local)

### Installation (work-in-progress)

```powershell
git clone git@github.com:chipat-neko/jarvis.git d:\assistant_ai\jarvis
cd d:\assistant_ai\jarvis

# Python workspace
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]                                    # tooling transverse (ruff, mypy, pytest)
pip install -e services/jarvis-orchestrator              # orchestrateur (CLI chat)
pip install -e services/jarvis-llm                       # routeur LLM hybride local/cloud
# (Les autres services seront installables une fois leur code écrit aux sprints S2+)

# Rust workspace
cargo build --workspace

# Ollama (~5 GB)
ollama pull qwen2.5:14b-instruct-q4_K_M
```

### Configuration

- Copier `config/config.example.yaml` → `config/local.yaml` (gitignored) et remplir
- **Aucune clé API requise** : Jarvis tourne 100% local via Ollama. Privacy by default.

### Lancer le chat (MVP texte, 100% local)

```powershell
py -3.11 -m orchestrator.chat                                  # qwen3:14b (défaut)
py -3.11 -m orchestrator.chat --ollama-model gpt-oss:120b      # top qualité mais 2 min cold start
py -3.11 -m orchestrator.chat --backend hf                     # backend HuggingFace
py -3.11 -m orchestrator.chat --via-grpc                       # via jarvis-llm:50052
```

Override permanent du modèle : `$env:JARVIS_LLM_MODEL = "..."`.

Guide complet : [`docs/quickstart.md`](docs/quickstart.md).

---

## Documentation interne

- **Blueprint final** : `d:/assistant_ai/recherche/100-jarvis-final-blueprint/`
- **Roadmap 14-15 semaines** : `d:/assistant_ai/recherche/99-jarvis-roadmap/`
- **Comparatif hardware** : `d:/assistant_ai/recherche/hardware-comparatif-noah/`
- **100 sujets de recherche** : `d:/assistant_ai/recherche/index.html`
- **Architecture Decision Records (ADR)** : [`docs/adr/`](docs/adr/) — décisions structurantes versionnées
  - [ADR-0001 : Microservices Python + Rust + gRPC](docs/adr/0001-microservices-python-rust.md)

---

## Roadmap (résumé 14-15 semaines)

| Phase | Semaines | Objectif |
|---|---|---|
| Foundation | S1-S2 | Setup environnement + toolchain Rust, LLM cœur local + cloud |
| Voice IO | S3-S4 | STT/VAD, wake word, TTS, pipeline Pipecat (Rust côté `jarvis-voice`) |
| Memory + Tools | S5-S6 | Mem0 + sqlite-vec, 8 MCP servers, gRPC inter-services |
| PC Control | S7-S8 | OmniParser local + LLM local Ollama (vision-capable), Open Interpreter, browser-use |
| Orchestration | S9-S10 | LangGraph state machines, multi-screen aware |
| Polish & Safety | S11-S12 | Kill switch, audit log, service Windows, observability stack |

Détail par sprint dans les cards Trello correspondantes.

---

## Licence

**Privé — tous droits réservés.**
Pas de redistribution, pas d'usage commercial, pas de fork public. Code perso.

---

🤖 *Projet co-piloté avec Claude (Anthropic) via Claude Code et l'API Computer Use.*
