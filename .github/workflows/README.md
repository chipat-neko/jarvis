# .github/workflows/

CI/CD GitHub Actions pour Jarvis.

## Workflows prevus (carte Trello CI multi-services)

- `python-services.yml` : ruff + mypy + pytest sur tous les services Python (matrix)
- `rust-services.yml`   : cargo fmt + clippy + test sur le workspace Rust
- `proto-codegen.yml`   : verifie que les .proto compilent

A creer lors du sprint CI dedie. Pour l'instant : skeleton.
