# Playbooks Ansible (actions de remédiation)

Règle : **une action = un playbook**. Le moteur de remédiation ne fait que les déclencher, avec une liste blanche d'actions et de services.

## Actions

| Action | Rôle | Paramètres |
|---|---|---|
| `restart` | Redémarre un service, attend qu'il soit prêt, recharge nginx si besoin | `service=` |
| `verify` | Vérifie que le service est prêt et que la chaîne répond (preuve de reprise) | `service=`, `check_url=` (optionnel) |
| `restore` | Restaure la base depuis un dump (sauvegarde d'abord l'état actuel dans `backups/pre_restore_*.sql`) | `confirm=yes`, `dump=` (optionnel, défaut `latest.sql`) |
| `isolate` | Retire un service de ses réseaux, il reste démarré pour l'analyse | `service=` |
| `unisolate` | Reconnecte un service isolé | `service=` |

Services autorisés : voir `group_vars/all.yml` (`allowed_services`, `isolatable_services`).

## Utilisation

Ansible tourne dans WSL2 (Ubuntu) et pilote Docker Desktop. Installation :

```bash
sudo apt update && sudo apt install -y ansible
docker ps        # doit lister les conteneurs (intégration WSL de Docker Desktop)
```

Depuis la racine du projet :

```bash
bash infra/ansible/run.sh restart service=backend
bash infra/ansible/run.sh verify service=backend
bash infra/ansible/run.sh isolate service=frontend
bash infra/ansible/run.sh unisolate service=frontend
bash infra/ansible/run.sh restore confirm=yes
```

Code de sortie : `0` = action réussie, autre = échec (le détail est dans la sortie). Toute action ou paramètre hors liste est refusé.

## Points d'attention

- Redémarrer le backend ou le frontend change leur adresse : nginx est donc rechargé ensuite (sinon erreur 502).
- `restore` arrête le backend pendant la restauration (tout ou rien), puis le redémarre, même en cas d'échec.
- Un dump peut contenir des données déjà corrompues : choisir un `dump=` plus ancien si besoin (12 versions, 1 h d'historique).
- Le blocage d'IP (`block_ip`) viendra après la décision de l'équipe sur le WAF et l'IP réelle.
