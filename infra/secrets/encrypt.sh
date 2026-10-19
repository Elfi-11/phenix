#!/usr/bin/env bash
# Chiffre .env en .env.enc (puis commiter .env.enc)
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo ".env introuvable" >&2; exit 1; }
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
grep -v '^[[:space:]]*$' .env > "$tmp"
sops encrypt --filename-override .env --input-type dotenv --output-type dotenv --output .env.enc "$tmp"
echo ".env.enc mis a jour : pensez a le commiter"
