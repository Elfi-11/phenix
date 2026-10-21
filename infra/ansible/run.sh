#!/usr/bin/env bash
# Lance une action de remédiation (liste blanche). Usage : bash infra/ansible/run.sh <action> [cle=valeur ...]
# Exemples : bash infra/ansible/run.sh restart service=backend
#            bash infra/ansible/run.sh restore confirm=yes
# Code de sortie : 0 = action réussie, autre = échec.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
action="${1:-}"
case "$action" in
  restart|verify|restore|isolate|unisolate|block_ip|unblock_ip|list_blocked|purge_expired) ;;
  *) echo "Action refusée ou manquante : '$action' (autorisées : restart verify restore isolate unisolate block_ip unblock_ip list_blocked purge_expired)" >&2; exit 2 ;;
esac
shift
args=()
for kv in "$@"; do
  case "$kv" in
    *=*) args+=(-e "$kv") ;;
    *) echo "Paramètre invalide : '$kv' (attendu : cle=valeur)" >&2; exit 2 ;;
  esac
done
export ANSIBLE_CONFIG="$here/ansible.cfg"
exec ansible-playbook -i "$here/inventory.ini" "$here/playbooks/$action.yml" "${args[@]}"
