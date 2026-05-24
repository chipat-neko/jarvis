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
