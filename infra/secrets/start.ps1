# Demarre la plateforme puis le moteur SQL dans ce terminal.
# Le fichier temporaire SOPS est supprime apres Compose ; le secret du moteur
# est transmis par l'environnement du processus, jamais comme argument.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not $env:SOPS_AGE_KEY_FILE) { $env:SOPS_AGE_KEY_FILE = Join-Path $HOME ".sops\keys.txt" }
if (-not (Test-Path $env:SOPS_AGE_KEY_FILE)) {
    throw "Cle introuvable : $env:SOPS_AGE_KEY_FILE (voir infra/secrets/README.md)"
}

# Le build fabrique le programme ; l'artefact entraine reste sur le PC hote.
# Refuser un demarrage incomplet plutot que lancer une detection sans modele.
if (-not (Test-Path "backend/ML/experiments/local-sql-v1/model.joblib")) {
    throw "Modele SQL absent : backend/ML/experiments/local-sql-v1/model.joblib"
}
if (-not (Test-Path "remediation/start_sql.py")) {
    throw "Lanceur absent : remediation/start_sql.py"
}
python -c "import requests"
if ($LASTEXITCODE -ne 0) { throw "Installer requests sur le PC hote : python -m pip install requests" }
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
if ($LASTEXITCODE -ne 0) { throw "Construction du detecteur SQL impossible" }

# Nom temporaire unique : ne pas reutiliser un fichier de secrets d'un autre lancement.
$tmp = Join-Path $env:TEMP ("phenix-" + [guid]::NewGuid().ToString("N") + ".env")
$previousPassword = $env:DEMO_USER_PASSWORD
$previousEnvFile = $env:ENV_FILE
$previousNetwork = $env:LOKI_DOCKER_NETWORK
try {
    try {
        sops decrypt --input-type dotenv --output-type dotenv --output $tmp .env.enc
        if ($LASTEXITCODE -ne 0) { throw "Dechiffrement impossible" }
        $env:ENV_FILE = $tmp
        docker compose --env-file $tmp up -d --build --remove-orphans
        if ($LASTEXITCODE -ne 0) { throw "Demarrage Compose impossible" }
        docker compose --env-file $tmp ps
        if ($LASTEXITCODE -ne 0) { throw "Lecture de l'etat Compose impossible" }

        # Recuperer le meme mot de passe que le backend, sans reparser dotenv.
        # La sortie est capturee ; ne pas l'afficher ni l'inclure dans un journal.
        $passwordOutput = docker compose --env-file $tmp exec -T backend python -c "import os,sys; sys.stdout.write(os.environ.get(sys.argv[1],str()))" DEMO_USER_PASSWORD
        if ($LASTEXITCODE -ne 0) { throw "Lecture du secret de service impossible" }
        $env:DEMO_USER_PASSWORD = [string]($passwordOutput -join "`n")
        $passwordOutput = $null
        if ([string]::IsNullOrEmpty($env:DEMO_USER_PASSWORD)) { throw "DEMO_USER_PASSWORD absent du backend" }

        # Decouvrir le reseau Loki du projet courant plutot que supposer son nom.
        if (-not $env:LOKI_DOCKER_NETWORK) {
            $lokiId = docker compose --env-file $tmp ps -q loki
            if ($LASTEXITCODE -ne 0 -or -not $lokiId) { throw "Conteneur Loki introuvable" }
            $networkJson = docker inspect --format '{{json .NetworkSettings.Networks}}' $lokiId
            if ($LASTEXITCODE -ne 0) { throw "Inspection du reseau Loki impossible" }
            $networkNames = @((($networkJson -join "") | ConvertFrom-Json).PSObject.Properties.Name)
            if ($networkNames.Count -ne 1) { throw "Plusieurs reseaux Loki : definir LOKI_DOCKER_NETWORK explicitement" }
            $env:LOKI_DOCKER_NETWORK = $networkNames[0]
        }
    }
    finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
        if ($null -eq $previousEnvFile) { Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue }
        else { $env:ENV_FILE = $previousEnvFile }
    }

    # Conserver le proxy Windows existant, puis attendre le vrai chemin utilisateur.
    Get-Process caddy -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Process caddy -ArgumentList "run","--config","infra\caddy\Caddyfile","--adapter","caddyfile" -WindowStyle Hidden
    Write-Host "Caddy demarre sur le port 8080 (vers le WAF sur 127.0.0.1:8081)"
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8080/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        }
        catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Plateforme lancee mais /health indisponible : moteur SQL non demarre" }

    # Processus au premier plan : ses alertes et erreurs restent visibles.
    # Ctrl+C arrete le moteur ; les conteneurs lances avec -d restent demarres.
    Write-Host "Demarrage du moteur SQL actif. Ctrl+C arrete le moteur, pas les conteneurs."
    python -u remediation/start_sql.py
    if ($LASTEXITCODE -ne 0) { throw "Le moteur SQL s'est arrete en erreur" }
}
finally {
    # Retirer le secret charge par ce script et restaurer l'environnement initial.
    if ($null -eq $previousPassword) { Remove-Item Env:DEMO_USER_PASSWORD -ErrorAction SilentlyContinue }
    else { $env:DEMO_USER_PASSWORD = $previousPassword }
    if ($null -eq $previousNetwork) { Remove-Item Env:LOKI_DOCKER_NETWORK -ErrorAction SilentlyContinue }
    else { $env:LOKI_DOCKER_NETWORK = $previousNetwork }
    $previousPassword = $null
}
