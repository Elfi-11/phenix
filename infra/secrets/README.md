# Secrets (SOPS + age)

- `.env.enc` : secrets chiffres, dans Git.
- `.env` : secrets en clair, local, ignore par Git. Ne jamais le commiter.
- Cle privee partagee de l'equipe : `%USERPROFILE%\.sops\keys.txt` (Linux/WSL : `~/.sops/keys.txt`).
  Elle se transmet par canal prive, jamais dans Git.

## Utilisation
| Action | Windows (PowerShell) | Linux / WSL |
|---|---|---|
| Recuperer les secrets | `.\infra\secrets\decrypt.ps1` | `infra/secrets/decrypt.sh` |
| Modifier un secret | modifier `.env`, puis `.\infra\secrets\encrypt.ps1` | `infra/secrets/encrypt.sh` |
| Tout demarrer (sans .env en clair) | `.\infra\secrets\start.ps1` | `infra/secrets/start.sh` |

Apres une modification, commiter `.env.enc`.

## Fonctionnement
`start` dechiffre `.env.enc` dans un fichier temporaire, lance `docker compose` avec, puis le supprime. Le compose lit `${ENV_FILE:-.env.example}` : sans le script, ce sont les valeurs factices du `.env.example` qui sont utilisees. Toujours demarrer avec `start`.
Pour modifier un secret : `decrypt` (cree `.env`), modifier, `encrypt`, supprimer `.env`.

## Limites (a mentionner dans le dossier)
- Une cle partagee par toute l'equipe : en cas de fuite, creer une nouvelle cle, rechiffrer et changer les secrets.
- Les secrets restent visibles dans l'environnement des conteneurs. Vault serait l'evolution pour la production.
