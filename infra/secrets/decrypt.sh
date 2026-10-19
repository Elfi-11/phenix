#!/usr/bin/env bash
# Dechiffre .env.enc en .env. Usage : infra/secrets/decrypt.sh [--force]
# Sous WSL : SOPS_AGE_KEY_FILE=/mnt/c/Users/<nom>/.sops/keys.txt infra/secrets/decrypt.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.sops/keys.txt}"
if [ ! -f "$SOPS_AGE_KEY_FILE" ]; then
  echo "Cle introuvable : $SOPS_AGE_KEY_FILE (voir infra/secrets/README.md)" >&2
  exit 1
fi
if [ -f .env ] && [ "${1:-}" != "--force" ]; then
  echo ".env existe deja (utiliser --force pour l'ecraser)"
  exit 0
fi
sops decrypt --input-type dotenv --output-type dotenv --output .env .env.enc
chmod 600 .env
echo ".env genere"
