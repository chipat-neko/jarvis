# scripts/codegen_python.ps1
#
# Génère le code Python à partir des fichiers .proto.
#
# Pour chaque service Python qui en a besoin, génère les modules dans
# services/jarvis-<service>/src/jarvis_<service>/proto_gen/.
#
# Pré-requis :
#   pip install grpcio grpcio-tools
#
# Usage :
#   pwsh -File scripts/codegen_python.ps1

$ErrorActionPreference = "Stop"

# Localise la racine du repo (parent de scripts/)
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProtoDir = Join-Path $RepoRoot "proto"
$ProtoFiles = Get-ChildItem -Path $ProtoDir -Filter "*.proto" -File

if ($ProtoFiles.Count -eq 0) {
    Write-Error "Aucun .proto trouvé dans $ProtoDir"
    exit 1
}

Write-Host "📦 Codegen Python depuis $ProtoDir" -ForegroundColor Cyan
Write-Host "   Fichiers : $($ProtoFiles.Name -join ', ')" -ForegroundColor DarkGray

# Quels services ont besoin de quels .proto
# Convention : chaque service a besoin de common.proto + son propre proto + ceux qu'il appelle
$ServiceProtos = @{
    "jarvis-orchestrator" = @("common", "voice", "llm", "cu", "tools", "memory", "safety")  # orchestrator appelle tout le monde
    "jarvis-llm"          = @("common", "llm")
    "jarvis-cu"           = @("common", "cu")
    "jarvis-tools"        = @("common", "tools")
    "jarvis-memory"       = @("common", "memory")
    "jarvis-ui"           = @("common")  # pour l'instant juste common, ajoutera selon besoins
    "jarvis-safety"       = @("common", "safety")
}

foreach ($svc in $ServiceProtos.Keys) {
    if ($svc -eq "jarvis-orchestrator") {
        $modName = "orchestrator"
    } else {
        $modName = $svc -replace "-", "_"
    }
    $genDir = Join-Path $RepoRoot "services/$svc/src/$modName/proto_gen"

    # Recrée le dossier proto_gen (clean state)
    if (Test-Path $genDir) { Remove-Item -Recurse -Force $genDir }
    New-Item -ItemType Directory -Force -Path $genDir | Out-Null

    # __init__.py minimal pour faire un package
    Set-Content -Path (Join-Path $genDir "__init__.py") `
                -Value "# Code généré par grpc_tools.protoc — NE PAS MODIFIER À LA MAIN.`n# Régénérer via : pwsh -File scripts/codegen_python.ps1`n" `
                -Encoding UTF8

    # Construit la liste des .proto à compiler pour ce service
    $protosToCompile = $ServiceProtos[$svc] | ForEach-Object { Join-Path $ProtoDir "$_.proto" }

    Write-Host "  → $svc : $($ServiceProtos[$svc] -join ', ')" -ForegroundColor Yellow

    # Invoque protoc avec les plugins Python + gRPC
    # --pyi_out pour générer les stubs typés (.pyi)
    python -m grpc_tools.protoc `
        --proto_path=$ProtoDir `
        --python_out=$genDir `
        --pyi_out=$genDir `
        --grpc_python_out=$genDir `
        $protosToCompile

    if ($LASTEXITCODE -ne 0) {
        Write-Error "protoc a échoué pour $svc (exit $LASTEXITCODE)"
        exit 1
    }
}

Write-Host ""
Write-Host "✅ Codegen Python terminé. Modules générés :" -ForegroundColor Green
foreach ($svc in $ServiceProtos.Keys) {
    if ($svc -eq "jarvis-orchestrator") {
        $modName = "orchestrator"
    } else {
        $modName = $svc -replace "-", "_"
    }
    $genDir = Join-Path $RepoRoot "services/$svc/src/$modName/proto_gen"
    $files = Get-ChildItem -Path $genDir -Filter "*.py" -File -ErrorAction SilentlyContinue
    Write-Host "   services/$svc/src/$modName/proto_gen/ ($($files.Count) fichiers)" -ForegroundColor DarkGreen
}
