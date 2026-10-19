# Chiffre .env en .env.enc (a lancer apres chaque modification du .env, puis commiter .env.enc)
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not (Test-Path .env)) { Write-Error ".env introuvable"; exit 1 }
$clean = Join-Path $env:TEMP "env.clean"
try {
    $lines = [System.IO.File]::ReadAllLines("$PWD\.env") | Where-Object { $_.Trim() -ne "" }
    [System.IO.File]::WriteAllText($clean, (($lines -join "`n") + "`n"))
    sops encrypt --filename-override .env --input-type dotenv --output-type dotenv --output .env.enc $clean
    if ($LASTEXITCODE -ne 0) { Write-Error "Echec du chiffrement"; exit 1 }
    Write-Host ".env.enc mis a jour : pensez a le commiter"
}
finally {
    Remove-Item $clean -ErrorAction SilentlyContinue
}
