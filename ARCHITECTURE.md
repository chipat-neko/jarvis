# Architecture Jarvis

> Détail technique de l'architecture cible. Vue d'ensemble dans [README.md](README.md).
> Décision actée : voir [ADR-0001](docs/adr/0001-microservices-python-rust.md).

---

## Vue d'ensemble — microservices avec gRPC localhost

```
┌─────────────────────────────────────────────────────────────────────┐
│              SATELLITES (ESP32-S3-BOX-3, ×2-3)                       │
│              Wake Word local · Relay audio HA                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Wyoming / HA Assist (LAN)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│      PC PRINCIPAL — Ryzen 7 9800X3D + RTX 5070 Ti                    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  jarvisd (jarvis-orchestrator, Python)                      │     │
│  │  ├─ Pipecat pipeline temps réel                             │     │
│  │  └─ LangGraph state machine                                 │     │
│  └─────┬─────────┬──────────┬──────────┬──────────┬──────────┘     │
│        │ gRPC    │ gRPC     │ gRPC     │ gRPC     │ gRPC            │
│   ┌────▼────┐ ┌──▼─────┐ ┌──▼─────┐ ┌──▼─────┐ ┌──▼─────┐          │
│   │ voice   │ │  llm   │ │   cu   │ │ tools  │ │ memory │          │
│   │ (Rust)  │ │(Python)│ │(Python)│ │(Python)│ │(Python)│          │
│   │ :50051  │ │ :50052 │ │ :50053 │ │ :50054 │ │ :50055 │          │
│   └─────────┘ └────────┘ └────────┘ └────────┘ └────────┘          │
│                                                                      │
│   ┌──────────┐  ┌────────────┐                                      │
│   │ jarvis-ui│  │jarvis-safety│  ← kill switch HW, audit, blacklist │
│   │ (Qt)     │  │(Python+Rust)│                                      │
│   │ :50056   │  │ :50057      │                                      │
│   └──────────┘  └─────────────┘                                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST / WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Home Assistant (Pi 5, Phase 2)                          │
│         Zigbee · Matter · Caméras · Capteurs IoT                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Pourquoi microservices** : isolation des crashs (un service qui meurt ne tue pas les autres), restart granulaire, observabilité par service. Pourquoi Rust pour `voice` : latence sub-100 ms STT→TTS impossible avec le GIL Python.

Cf [ADR-0001](docs/adr/0001-microservices-python-rust.md) pour les alternatives écartées et les conséquences détaillées.

---

## Services

Chaque service vit dans `services/jarvis-<nom>/` avec :

- Python : `pyproject.toml` + `src/jarvis_<nom>/` + `tests/` + entry point `jarvis_<nom>.main:main`
- Rust : `Cargo.toml` (référencé par le workspace racine) + `src/main.rs` + `build.rs` pour codegen proto

### `jarvis-orchestrator` (Python)

Service maître. Point d'entrée du daemon `jarvisd`. Démarre la pipeline Pipecat + le state machine LangGraph, et orchestre les appels gRPC vers les autres services.

- `src/orchestrator/core/` — config, logger, démarrage
- `src/orchestrator/speech/` — wrappers vers `jarvis-voice` (proxies gRPC)
- `src/orchestrator/nlp/` — wrappers vers `jarvis-llm` (intent + completion)
- `src/orchestrator/actions/` — skills (home_automation, calendar, email, websearch, music, ...)
- `src/orchestrator/utils/` — helpers

### `jarvis-voice` (Rust)

Pipeline voice temps réel. Cible perf : < 100 ms STT→TTS.

- `src/main.rs` — gRPC server `:50051`
- `build.rs` — codegen `voice.proto` + `common.proto` via `tonic-build`
- Sprints d'implémentation : S3 (STT/VAD/audio capture), S4 (wake word + TTS + Pipecat-compatible)

### `jarvis-llm` (Python)

LLM router local (Ollama Qwen 3.5 14B Q4) + cloud (Anthropic Sonnet 4.6). Décide qui répond selon intent simple/complexe, token count, latence tolérée. Prompt caching Anthropic activé.

### `jarvis-cu` (Python)

Computer Use : Anthropic CU + OmniParser local GPU pour Set-of-Mark. PyAutoGUI pour input synthesis. Audit chaque action via `jarvis-safety`.

### `jarvis-tools` (Python)

Wrappers MCP servers (filesystem, github, brave, home-assistant, spotify, gmail, notion, memory). Expose une interface gRPC unifiée à `jarvis-orchestrator`.

### `jarvis-memory` (Python)

Mem0 + sqlite-vec local + embeddings BGE-large. Recall sémantique pour conversations long terme.

### `jarvis-ui` (Python)

HUD Qt frameless transparent, multi-écran (3 displays détectés sur le hardware Noah), hotkeys globaux (push-to-talk, panic hide, kill switch), systray.

### `jarvis-safety` (Python + Rust)

Couche de protection critique :

- Kill switch hardware (Pi Pico W + bouton) → endpoint FastAPI local
- Audit log SQLite (WAL mode, retention 90j)
- Blacklist YAML (URLs bancaires, paths système, process protégés)
- Confirmations vocales pour actions risquées (delete, send email, transfer money, install app)
- Partie Rust : pour le hot path d'audit (logging haute fréquence)

---

## Communication inter-services (gRPC)

Tous les contrats sont dans [`proto/`](proto/). Chaque service écoute sur un port `:5005X` distinct sur localhost.

Convention :

- Package `jarvis.<service>.v1` — bump `v2` si breaking change
- Ne JAMAIS supprimer un field — utiliser `reserved`
- Codegen Python : script `scripts/codegen_python.sh` → `python -m grpc_tools.protoc` → modules `jarvis_<service>/proto_gen/`
- Codegen Rust : `tonic-build` invoqué depuis `build.rs` au `cargo build`

Pour l'instant chaque service expose juste un RPC `Ping/Pong` — les vrais contrats seront définis lors de l'implémentation du service correspondant (cf TODO dans chaque `.proto`).

---

## Pipeline temps réel (vue logique)

```
microphone audio stream
  → VAD (Silero) découpe les segments parlés      ┐
  → Wake word detection ("Hey Jarvis")            │ jarvis-voice (Rust, :50051)
  → STT (Whisper large-v3-turbo CUDA)             ┘
  → Intent classifier rapide (jarvis-llm)         ┐
  → Decision routing local vs cloud               │ jarvis-llm (Python, :50052)
  → Execution (LLM + tool calls + CU)             ┘
  → Response synthesis
  → TTS (Chatterbox GPU)                          ─ jarvis-voice (Rust, :50051)
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
| Tool calling (MCP) | Sonnet 4.6 (tool use le plus robuste) |
| Génération longue / résumé doc | Sonnet 4.6 |
| Translation rapide | Local Qwen 14B |

Le router est dans `jarvis-llm/src/jarvis_llm/router.py` (à écrire en S2).

---

## Observability

Stack à mettre en place en parallèle des services (cf carte Trello `📊 Setup observability stack`) :

- **Prometheus** scrape `/metrics` de chaque service (Python : `prometheus-client`, Rust : `metrics-exporter-prometheus`)
- **Grafana** dashboards : `voice-pipeline.json` (latence STT/TTS/end-to-end), `llm-routing.json` (tokens, coûts, local vs cloud), `system.json` (CPU/RAM/GPU par service)
- **LangSmith** pour tracer les appels LLM (free tier 5k traces/mois)

Configs dans [`infra/`](infra/).

---

## Safety / Security

Couches de protection (cf carte Trello `🩷 Safety / Security` + `jarvis-safety`) :

1. **Kill switch hardware** (Pi Pico W + bouton arcade) → POST `localhost:8765/kill` coupe TOUS les services Jarvis en < 100 ms
2. **Audit log SQLite** : toutes les actions CU + appels MCP + intents + outputs (retention 90j)
3. **Blacklist YAML** : URLs (sites bancaires), paths système (`/etc/`, `%Windir%`), process protégés (antivirus, password manager)
4. **Confirmation vocale** : delete file, send email, transfer money, install app → demande "oui" explicite
5. **Sandboxing** : code généré par LLM exécuté dans Docker container, jamais directement
6. **Secrets en keyring OS** : jamais en `.env` commit, jamais dans le code

---

## Coûts ops estimés (mensuel)

| Poste | Estimation | Note |
|---|---|---|
| Sonnet 4.6 API (avec prompt caching) | 30-50 € | Selon usage |
| LLM local (élec GPU) | ~5 € | RTX 5070 Ti idle bas |
| Whisper STT local | 0 € | GPU local (Rust) |
| TTS Chatterbox local | 0 € | GPU local |
| HA + add-ons | 0 € | Self-host |
| **Total** | **~40-60 €/mois** | Très soutenable |

---

## Roadmap technique

Voir [README.md#roadmap](README.md#roadmap-résumé-14-15-semaines) et le board Trello pour le détail sprint par sprint.
