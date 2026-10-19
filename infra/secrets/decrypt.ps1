# Dechiffre .env.enc en .env (a la racine du projet)
# Usage : .\infra\secrets\decrypt.ps1        (ne fait rien si .env existe)
#         .\infra\secrets\decrypt.ps1 -Force (ecrase le .env)
param([switch]$Force)
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not $env:SOPS_AGE_KEY_FILE) { $env:SOPS_AGE_KEY_FILE = Join-Path $HOME ".sops\keys.txt" }
if (-not (Test-Path $env:SOPS_AGE_KEY_FILE)) {
    Write-Error "Cle introuvable : $env:SOPS_AGE_KEY_FILE (a recevoir de Yannick, voir infra/secrets/README.md)"
    exit 1
}
if ((Test-Path .env) -and -not $Force) {
    Write-Host ".env existe deja (utiliser -Force pour l'ecraser)"
    exit 0
}
sops decrypt --input-type dotenv --output-type dotenv --output .env .env.enc
if ($LASTEXITCODE -ne 0) { Write-Error "Echec du dechiffrement"; exit 1 }
Write-Host ".env genere"
