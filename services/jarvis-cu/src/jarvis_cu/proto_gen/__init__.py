"""Code généré par grpc_tools.protoc — NE PAS MODIFIER À LA MAIN.

Régénérer via : pwsh -File scripts/codegen_python.ps1 (ou inline équivalent).

NOTE TECHNIQUE : grpc_tools.protoc génère des `import common_pb2` directs
(et non `from . import common_pb2`). On ajoute ce dossier au sys.path pour
que ces imports résolvent. Solution propre future : utiliser `protoletariat`
ou un post-processing regex dans le script de codegen.
"""

import os
import sys

# Permet aux imports inter-protos (import common_pb2, import voice_pb2, ...)
# de fonctionner depuis ce package.
_gen_dir = os.path.dirname(os.path.abspath(__file__))
if _gen_dir not in sys.path:
    sys.path.insert(0, _gen_dir)
