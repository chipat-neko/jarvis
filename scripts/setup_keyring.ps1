# scripts/setup_keyring.ps1
#
# Helper pour stocker la cle API Anthropic dans le keyring Windows
# (Credential Manager). Une fois stockee, Jarvis la recupere automatiquement
# via jarvis_llm.secrets.get_anthropic_api_key().
#
# Usage :
#   py -3.11 -File scripts\setup_keyring.ps1
#
# Note : le script prompt pour la cle (input cache). N'est PAS commit dans git.

$ErrorActionPreference = "Stop"

Write-Host "Configuration du keyring Windows pour Jarvis" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service : jarvis" -ForegroundColor DarkGray
Write-Host "Username : anthropic_api_key" -ForegroundColor DarkGray
Write-Host ""

# Verifie que le module keyring est dispo
$check = py -3.11 -c "import keyring; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Module 'keyring' indisponible. Install :" -ForegroundColor Red
    Write-Host "  py -3.11 -m pip install keyring" -ForegroundColor Yellow
    exit 1
}

$secureKey = Read-Host -Prompt "Colle ta cle Anthropic (sk-ant-...)" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$plainKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) | Out-Null

if (-not $plainKey -or -not $plainKey.StartsWith("sk-ant-")) {
    Write-Host "Cle vide ou format invalide (doit commencer par 'sk-ant-')." -ForegroundColor Red
    exit 2
}

# Stocke via le module keyring de Python (cross-platform)
$plainKey | py -3.11 -c "import sys, keyring; keyring.set_password('jarvis', 'anthropic_api_key', sys.stdin.read().strip())"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Echec du stockage." -ForegroundColor Red
    exit 3
}

# Verification
$verify = py -3.11 -c "from jarvis_llm.secrets import get_anthropic_api_key; print('OK' if get_anthropic_api_key() else 'KO')" 2>&1
Write-Host ""
if ($verify -match "OK") {
    Write-Host "Cle stockee avec succes." -ForegroundColor Green
    Write-Host "Tu peux maintenant lancer :" -ForegroundColor Green
    Write-Host "  py -3.11 -m orchestrator.chat" -ForegroundColor Yellow
} else {
    Write-Host "Stockage OK mais verification echouee. Verifie l'install jarvis-llm." -ForegroundColor Yellow
}
