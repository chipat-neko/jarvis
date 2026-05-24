#!/usr/bin/env bash
# scripts/codegen_python.sh
#
# Génère le code Python à partir des fichiers .proto.
# Équivalent bash de codegen_python.ps1 (pour Linux / WSL / macOS).
#
# Pré-requis :
#   pip install grpcio grpcio-tools
#
# Usage :
#   bash scripts/codegen_python.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO_DIR="${REPO_ROOT}/proto"

if ! ls "${PROTO_DIR}"/*.proto >/dev/null 2>&1; then
    echo "Erreur : aucun .proto trouvé dans ${PROTO_DIR}" >&2
    exit 1
fi

echo "📦 Codegen Python depuis ${PROTO_DIR}"

# Map service → liste des protos dont il a besoin
declare -A SERVICE_PROTOS=(
    ["jarvis-orchestrator"]="common voice llm cu tools memory safety"
    ["jarvis-llm"]="common llm"
    ["jarvis-cu"]="common cu"
    ["jarvis-tools"]="common tools"
    ["jarvis-memory"]="common memory"
    ["jarvis-ui"]="common"
    ["jarvis-safety"]="common safety"
)

for svc in "${!SERVICE_PROTOS[@]}"; do
    if [[ "${svc}" == "jarvis-orchestrator" ]]; then
        mod_name="orchestrator"
    else
        mod_name="${svc//-/_}"
    fi
    gen_dir="${REPO_ROOT}/services/${svc}/src/${mod_name}/proto_gen"

    # Recrée le dossier proto_gen (clean state)
    rm -rf "${gen_dir}"
    mkdir -p "${gen_dir}"

    # __init__.py — inclut un hack sys.path pour que les imports inter-protos
    # générés par grpc_tools.protoc (ex: `import common_pb2`) se résolvent.
    cat > "${gen_dir}/__init__.py" <<'EOF'
"""Code généré par grpc_tools.protoc — NE PAS MODIFIER À LA MAIN.

Régénérer via : bash scripts/codegen_python.sh (ou codegen_python.ps1).

NOTE TECHNIQUE : grpc_tools.protoc génère des `import common_pb2` directs
(et non `from . import common_pb2`). On ajoute ce dossier au sys.path pour
que ces imports résolvent. Solution propre future : protoletariat.
"""

import os
import sys

_gen_dir = os.path.dirname(os.path.abspath(__file__))
if _gen_dir not in sys.path:
    sys.path.insert(0, _gen_dir)
EOF

    # Construit la liste des protos à compiler
    protos=()
    for p in ${SERVICE_PROTOS[$svc]}; do
        protos+=("${PROTO_DIR}/${p}.proto")
    done

    echo "  → ${svc} : ${SERVICE_PROTOS[$svc]}"

    python -m grpc_tools.protoc \
        --proto_path="${PROTO_DIR}" \
        --python_out="${gen_dir}" \
        --pyi_out="${gen_dir}" \
        --grpc_python_out="${gen_dir}" \
        "${protos[@]}"
done

echo ""
echo "✅ Codegen Python terminé."
