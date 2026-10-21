# Scénario Red Team — rafale de connexions échouées

Projet RESILIENCE-ALPHA. Ce dossier contient l'attaque principale de la démonstration :
une rafale de tentatives de connexion échouées sur l'API de paiement.

## But

Générer un **signal observable** (beaucoup d'échecs d'authentification depuis une
même IP) pour déclencher la chaîne complète : **détection → remédiation automatique → reprise**.

Ce n'est **pas** du vol de compte : on envoie volontairement de **mauvais mots de
passe**. Les mots de passe réels sont protégés (bcrypt) et aucun compte n'est compromis.
Le scénario démontre la **disponibilité** : on détecte l'attaquant et on bloque son IP,
pendant qu'un client légitime continue de payer.

## ⚠️ Périmètre

À lancer **uniquement depuis le PC attaquant**, contre la **plateforme fictive de
l'équipe**. Toute autre cible (réseau du campus, autre groupe, service internet) est
**interdite** par le sujet.

## Prérequis (sur le PC attaquant)

1. Être connecté au point d'accès **RESILIENCE-G5** (celui du PC hôte).
2. Python installé : `python --version` (sinon `winget install Python.Python.3.12`, puis rouvrir le terminal).
3. Le module requests : `pip install requests`
4. Vérifier qu'on joint la plateforme — ouvrir dans le navigateur :
   `http://192.168.137.1:8080/health` doit afficher `{"status":"ok"}`.
   Sinon, voir Yannick (point d'accès, pare-feu).

## Lancer l'attaque

Depuis ce dossier :

```powershell
python attaque_login.py
```

Par défaut : 60 tentatives sur `alice_client`, une toutes les 0,2 s, vers `http://192.168.137.1:8080`.

### Options

```powershell
python attaque_login.py --essais 100          # plus de tentatives
python attaque_login.py --delai 0.1           # plus rapide
python attaque_login.py --cible http://192.168.137.1:8080 --utilisateur bob_client
```

## Ce qu'on doit observer (sur le dashboard admin, PC hôte)

| Moment | Dashboard |
|---|---|
| Avant | 🟢 API opérationnelle, 0 incident, trafic calme |
| Pendant | Le trafic et les erreurs montent ; un incident apparaît |
| Remédiation | L'IP de l'attaquant est bloquée (le script reçoit des 403 ou des erreurs réseau) |
| Après | Incident résolu avec son temps de reprise ; un paiement de test repasse au vert |

## Détection associée

Chaque échec écrit une ligne `AUTH_FAILURE username=... ip=...` dans les logs du
backend (→ Loki). La règle SIEM « rafale d'échecs » (Grafana) se déclenche au-delà
du seuil, et le moteur de remédiation lance l'action `block_ip`.

## Réinitialiser entre deux essais

Si l'IP a été bloquée pendant une répétition, la débloquer avant de recommencer
(sur le PC hôte, dans WSL) :

```bash
bash infra/ansible/run.sh unblock_ip ip=<IP_DU_PC_ATTAQUANT>
bash infra/ansible/run.sh list_blocked
```
