# Demarre la plateforme avec les secrets de .env.enc (aucun .env en clair sur le disque)
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not $env:SOPS_AGE_KEY_FILE) { $env:SOPS_AGE_KEY_FILE = Join-Path $HOME ".sops\keys.txt" }
if (-not (Test-Path $env:SOPS_AGE_KEY_FILE)) {
    Write-Error "Cle introuvable : $env:SOPS_AGE_KEY_FILE (voir infra/secrets/README.md)"
    exit 1
}
$tmp = Join-Path $env:TEMP "phenix.env"
try {
    sops decrypt --input-type dotenv --output-type dotenv --output $tmp .env.enc
    if ($LASTEXITCODE -ne 0) { Write-Error "Dechiffrement impossible"; exit 1 }
    $env:ENV_FILE = $tmp
    docker compose --env-file $tmp up -d --build --remove-orphans
}
finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
}
docker compose ps

# Proxy Windows : ajoute la vraie IP du client (X-Forwarded-For)
Get-Process caddy -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Process caddy -ArgumentList "run","--config","infra\caddy\Caddyfile","--adapter","caddyfile" -WindowStyle Hidden
Write-Host "Caddy demarre sur le port 8080 (vers le WAF sur 127.0.0.1:8081)"