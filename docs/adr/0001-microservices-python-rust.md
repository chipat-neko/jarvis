# ADR-0001 : Architecture microservices Python + Rust avec communication gRPC

- **Statut** : Accepted
- **Date** : 2026-05-24
- **Décideurs** : Noah Trillon (+ Claude Opus 4.7)
- **Tags** : `archi`, `langage`, `microservices`, `grpc`

---

## Contexte

Le projet Jarvis vise un assistant vocal personnel avec contrôle 100 % du PC (multi-écran, smart home, mémoire long terme). Les besoins définissent l'architecture :

- **Latence cible** du pipeline voice end-to-end : < 1.5 s (wake → STT → LLM → TTS).
  - Pour atteindre cela, la portion STT/VAD/TTS doit tourner en sub-100 ms.
- **Isolation des crashs** : si le pipeline voice crash, l'agent ne doit pas mourir entièrement (l'audit log, le LLM cloud, etc. doivent rester debout).
- **Hardware validé** : Ryzen 7 9800X3D + RTX 5070 Ti 16GB + 64GB DDR5 + 3 écrans + 4.6 TB SSD (cf hardware-comparatif-noah).
- **Solo dev** : Noah travaille seul. Toute complexité supplémentaire doit être justifiée par un bénéfice concret.
- **Ambition** : projet sérieux destiné à durer 6+ mois, potentiellement extensible (open source plus tard si succès). Pas du throwaway code.
- **Roadmap** : MVP 12 semaines initial, accepté en passant à 14-15 semaines pour atteindre une qualité production-grade.

Trois profils ont été discutés lors du choix d'architecture (cf Trello card *Mise en place de l'architecture du projet* en Terminé) :

- **P1 — Pragmatique pro** : Python monolithique modulaire, simple à dev en solo mais latence voice limitée par le GIL.
- **P2 — Enterprise pro** : Python + Rust + microservices, sérieux et perf top, courbe d'apprentissage Rust à absorber.
- **P3 — R&D maximaliste** : monorepo polyglotte (Python + Rust + Zig) + DDD strict, intenable pour un solo en MVP 14-15 sem.

## Décision

**Architecture P2 — Enterprise pro adoptée**.

Concrètement :

- **Polyglotte Python + Rust**
  - **Python** : orchestration (LangGraph), LLM router (Sonnet 4.6 + Qwen 14B local), Computer Use, MCP servers, memory layer (Mem0 + sqlite-vec), UI Qt, safety.
  - **Rust** : pipeline voice critique (wake word, STT wrapper Whisper, VAD, TTS wrapper, audio I/O loopback WASAPI). Seul Rust permet d'atteindre la cible sub-100 ms sur ces étapes.

- **Style microservices locaux** : chaque domaine fonctionnel est un process séparé qui démarre/redémarre indépendamment. Communication via **gRPC sur localhost** (proto contracts versionnés dans `proto/`).
  - `jarvis-orchestrator` (Python, point d'entrée)
  - `jarvis-voice` (Rust)
  - `jarvis-llm` (Python)
  - `jarvis-cu` (Python, Computer Use + OmniParser)
  - `jarvis-tools` (Python, MCP)
  - `jarvis-memory` (Python)
  - `jarvis-ui` (Python, HUD Qt)
  - `jarvis-safety` (Python + Rust)

- **Origine du code** : *cherry-pick* — structure clean chez nous + import au cas par cas des composants éprouvés depuis les 10 deep dives GitHub du dossier de recherche (`gh01-gh10`) et les 2 projets référence (`isair/jarvis`, `TimLukaHorstmann/J.A.R.V.I.S`). Pas de fork direct.

- **Repo Git** : on garde le commit initial `5b901f0` (`chore: initial commit`) dans l'historique. Un commit `refactor:` séparé migrera vers la nouvelle structure microservices.

## Alternatives considérées

### Alternative A — P1 Pragmatique pro (Python pur, monolithe modulaire)

Python monolithique avec modules `jarvis/{voice,llm,cu,...}`, pytest, Ruff, mypy non-strict, Docker.

**Écartée car** :
- Latence pipeline voice limitée par le GIL Python (~150-250 ms STT→TTS au lieu de 50-80 ms en Rust).
- Aucune isolation : un crash dans voice tue tout l'agent (LLM, MCP, safety inclus).
- Couplage fort des modules ralentit l'évolution long terme.
- Noah veut explicitement « le plus professionnel, pas le plus simple ».

### Alternative B — P3 R&D maximaliste (Python + Rust + Zig + DDD strict)

Monorepo polyglotte, design DDD hexagonal, mypy --strict, observability complète (Prometheus + Grafana + LangSmith + Sentry + OpenTelemetry), tests > 80 % coverage obligatoire.

**Écartée car** :
- Intenable en solo sur 14-15 semaines pour livrer un MVP fonctionnel — l'overhead d'architecture absorbe le temps de feature.
- Zig n'apporte rien que Rust ne fasse déjà bien sur ce projet.
- DDD strict + mypy --strict sur tout le codebase ralentit l'itération initiale (on apprend le domaine en construisant).
- Risque de ne jamais livrer car la barre architecturale est trop haute.

### Alternative C — Fork direct de `isair/jarvis` ou `TimLukaHorstmann/J.A.R.V.I.S`

Reprendre une base existante éprouvée et l'étendre.

**Écartée car** :
- Hérite des choix structurels de l'auteur original (souvent moins pro, monolithe Python).
- Couplage fort à la base, refactor difficile sans tout casser.
- Question de licence + attribution non triviale pour un projet privé personnel.
- Le bénéfice « démarrage rapide » est compensé par la dette dès la 2e semaine.

### Alternative D — Tout Python avec FFI (Cython/PyO3) pour les hot paths voice

Python global + extensions C/Rust ponctuelles pour les chemins critiques.

**Écartée car** :
- Garde le GIL sur tout sauf les rares hot paths C/Rust.
- Tooling de build hybride Python+Rust via PyO3 plus complexe à maintenir qu'un service Rust séparé (build.rs, pyproject avec extensions binaires, packaging).
- Pas d'isolation des crashs : un panic Rust dans un module FFI peut planter le process Python entier.

## Conséquences

### Positives

- ✅ **Latence voice cible atteignable** : Rust pour STT/VAD/TTS = 50-80 ms sub-100 ms réaliste.
- ✅ **Isolation des crashs** : un service qui meurt ne tue pas les autres (ex : crash voice n'empêche pas le LLM de répondre par texte).
- ✅ **Restart granulaire** : on peut redémarrer `jarvis-voice` après update sans tout couper.
- ✅ **Tests et CI par service** : matrix de tests indépendants, plus rapides.
- ✅ **Observability propre** : chaque service expose `/metrics` Prometheus indépendamment.
- ✅ **Évolutivité** : extraire un service ou en ajouter un nouveau ne touche pas les autres.
- ✅ **Apprentissage Rust valorisable** au-delà du projet Jarvis (perspective long terme Noah).
- ✅ **Code production-grade**, portfolio-worthy si Noah décide d'ouvrir le projet plus tard.

### Négatives / coûts assumés

- ⚠️ **Courbe d'apprentissage Rust** : ~2-3 semaines additionnelles sur la roadmap (12 → 14-15 sem). Accepté par Noah.
- ⚠️ **Complexité gRPC** : nécessite définir/maintenir des `.proto`, gérer codegen Python (`grpcio-tools`) + Rust (`tonic-build`), gérer les versions des schémas.
- ⚠️ **Plus de processus à orchestrer** : besoin de systemd / Windows Service Wrapper pour démarrer tout au boot et superviser les redémarrages.
- ⚠️ **Debug plus complexe** : un appel cross-service traverse au moins 2 process et leurs stacktraces. Mitigation : LangSmith + Prometheus tracing.
- ⚠️ **Overhead latence inter-services** : ~1-5 ms par appel gRPC localhost. Acceptable pour la plupart des cas mais à surveiller sur le chemin critique voice.

### Neutres / à surveiller

- ℹ️ Les schémas `.proto` deviennent un contrat de fait — toute évolution doit respecter la backward compat ou bumper une version.
- ℹ️ Toute decision d'ajouter une 9e ou 10e service doit être pesée (chaque service = coût de maintenance fixe).
- ℹ️ La sérialisation gRPC ajoute un coût CPU non-nul. Si certaines API deviennent très chaudes, envisager un buffer partagé ou un transport plus rapide (Unix domain socket en Linux, named pipe Windows).

## Plan d'application

1. **Refactor migration P2** (carte Trello `🔧 Refactor — Migration repo vers archi P2`) : 1 gros commit qui déplace `jarvis/{core,nlp,actions,...}` → `services/jarvis-orchestrator/` et crée la nouvelle structure complète.
2. **Setup Cargo workspace + skeleton `services/jarvis-voice/`** : premier service Rust avec gRPC server localhost:50051.
3. **Schemas gRPC `proto/`** : définir les contrats inter-services + codegen Python et Rust.
4. **CI multi-services** : workflows GitHub Actions (Python + Rust + protoc matrix).
5. **Observability stack** : Prometheus + Grafana via `infra/docker-compose.observability.yml`, LangSmith pour les traces LLM.
6. **Au fil des sprints suivants** : implémenter chaque service en respectant les contrats `.proto` et les conventions de log/metrics.

## Références

- **Carte Trello d'origine** : [Mise en place de l'architecture du projet](https://trello.com/c/T5vCV0wA) (questionnaire VSCode 6/6 validé)
- **Mémoire Claude** : `~/.claude/projects/d--assistant-ai/memory/project_jarvis_architecture.md`
- **Recherche complémentaire** : `d:/assistant_ai/recherche/100-jarvis-final-blueprint/` (stack finale retenue)
- **Hardware** : `d:/assistant_ai/recherche/hardware-comparatif-noah/`
- **Cartes de migration** :
  - 🔧 [Refactor migration P2](https://trello.com/c/aazpbq7a)
  - 🦀 [Cargo workspace + jarvis-voice](https://trello.com/c/rAQtDbQv)
  - 📡 [Schemas gRPC proto/](https://trello.com/c/kpM92zOe)
  - 🚦 [CI multi-services](https://trello.com/c/unDAJ0nW)
  - 📊 [Observability stack](https://trello.com/c/1M3Z8GO3)
