#!/usr/bin/env bash
# Demarre la plateforme avec les secrets de .env.enc (aucun .env en clair sur le disque)
set -euo pipefail
cd "$(dirname "$0")/../.."
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.sops/keys.txt}"
[ -f "$SOPS_AGE_KEY_FILE" ] || { echo "Cle introuvable : $SOPS_AGE_KEY_FILE" >&2; exit 1; }
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
chmod 600 "$tmp"
sops decrypt --input-type dotenv --output-type dotenv --output "$tmp" .env.enc
ENV_FILE="$tmp" docker compose --env-file "$tmp" up -d --build --remove-orphans
docker compose ps
