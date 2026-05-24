# proto/

Schemas gRPC partages par tous les services Jarvis (source of truth).

## Conventions

- **Versioning** : chaque package est `jarvis.<service>.v1`. On bump v2 si breaking change.
- **Champs reserves** : ne jamais supprimer un field, le passer en `reserved` pour eviter wire collisions.
- **Codegen** :
  - Python : `python -m grpc_tools.protoc --python_out=... --grpc_python_out=... -I. *.proto` (script a venir : `scripts/codegen_python.sh`)
  - Rust : `tonic-build` invoque depuis `services/jarvis-voice/build.rs` au `cargo build`
- **Pour l'instant** : tous les services exposent un simple `Ping/Pong` pour valider la chaine gRPC. Les vrais RPC seront ajoutes au fil des sprints (cf TODO dans chaque .proto).

## Index

| Schema | Service | Sprint cible |
|---|---|---|
| `common.proto`  | Types partages              | S6 (avec proto/) |
| `voice.proto`   | jarvis-voice (Rust)         | S3-S4 |
| `llm.proto`     | jarvis-llm                  | S2 |
| `cu.proto`      | jarvis-cu                   | S7 |
| `tools.proto`   | jarvis-tools                | S6 |
| `memory.proto`  | jarvis-memory               | S5 |
| `safety.proto`  | jarvis-safety               | S11 |

Cf [ADR-0001](../docs/adr/0001-microservices-python-rust.md).
