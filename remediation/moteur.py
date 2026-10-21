#!/usr/bin/env python3
"""Moteur de remédiation — Phenix (SQUELETTE à adapter par Léa / Richard).

Rôle : fermer la boucle « détection -> action -> reprise » SANS intervention humaine.
Il tourne en continu sur le PC hôte et, pour chaque alerte reçue :

    1. récupère un token (compte SERVICE)
    2. enregistre l'incident        -> POST  /api/incidents
    3. exécute l'action corrective  -> bash infra/ansible/run.sh <action>
    4. vérifie la reprise           -> bash infra/ansible/run.sh verify
    5. clôture l'incident           -> PATCH /api/incidents/{id}/resolve

CE QUI EST DÉJÀ ÉCRIT : les étapes 1 à 5 (dialogue avec l'API et Ansible).
CE QUI RESTE À FAIRE (Léa/Richard) : la fonction detecter_alertes() qui branche
le ML ou les alertes SIEM. Pour l'instant elle est simulée (voir plus bas).

Prérequis : plateforme démarrée, Ansible utilisable dans WSL (voir docs/pc-hote.md),
module requests (`pip install requests`).
"""
import platform
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Installez requests :  pip install requests")

# --- Configuration -------------------------------------------------------------------------------
API = "http://localhost:8080"          # la plateforme, vue depuis le PC hôte
SERVICE_USER = "service_remediation"   # compte SERVICE (droits limités aux incidents)
SERVICE_PASSWORD = "CHANGE_ME"         # mot de passe de démo (DEMO_USER_PASSWORD) — à injecter proprement
PROJECT_DIR = r"C:\Users\<toi>\phenix"  # racine du dépôt sur le PC hôte (pour WSL) — à adapter
INTERVALLE_S = 5                        # pause entre deux cycles de détection


# --- Étape 3 : lancer une action Ansible ---------------------------------------------------------
def action_ansible(action: str, **params) -> tuple[bool, str]:
    """Lance `bash infra/ansible/run.sh <action> clef=valeur`. Renvoie (succès, sortie)."""
    args = [f"{k}={v}" for k, v in params.items()]
    cmd = ["bash", "infra/ansible/run.sh", action, *args]
    if platform.system() == "Windows":
        cmd = ["wsl", "--cd", PROJECT_DIR, *cmd]   # sous Windows, Ansible tourne dans WSL
        cwd = None
    else:
        cwd = PROJECT_DIR
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    return r.returncode == 0, (r.stdout + r.stderr)[-500:]


# --- Dialogue avec l'API incidents (déjà prête, côté Marina) -------------------------------------
def get_token() -> str:
    r = requests.post(f"{API}/api/auth/login",
                      json={"username": SERVICE_USER, "password": SERVICE_PASSWORD}, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


def ouvrir_incident(token: str, alerte: dict) -> int:
    corps = {
        "event_type": alerte["event_type"],      # ex. "ML_ANOMALY_DETECTED" ou "AUTH_FAILURE"
        "severity": alerte["severity"],           # "INFO" | "WARNING" | "CRITICAL"
        "source": alerte["source"],               # "ML", "SIEM"...
        "target_service": alerte.get("target_service"),
        "description": alerte["description"],
    }
    r = requests.post(f"{API}/api/incidents", json=corps,
                      headers={"Authorization": f"Bearer {token}"}, timeout=5)
    r.raise_for_status()
    return r.json()["id"]


def resoudre_incident(token: str, incident_id: int, action_taken: str) -> None:
    r = requests.patch(f"{API}/api/incidents/{incident_id}/resolve",
                       json={"action_taken": action_taken},
                       headers={"Authorization": f"Bearer {token}"}, timeout=5)
    r.raise_for_status()


# --- Le cœur : traiter une alerte de bout en bout ------------------------------------------------
def traiter(token: str, alerte: dict) -> None:
    print(f"\n[ALERTE] {alerte['description']}")

    incident_id = ouvrir_incident(token, alerte)
    print(f"  incident #{incident_id} ouvert")

    # Choix de l'action selon l'alerte. Ici : bloquer l'IP d'un brute force.
    # À enrichir : restart si un service est tombé, restore si données corrompues...
    ok_action, sortie = action_ansible("block_ip", ip=alerte["ip"], reason="bruteforce")
    print(f"  block_ip : {'OK' if ok_action else 'ÉCHEC'}")

    ok_verif, _ = action_ansible("verify", service="backend")
    print(f"  verify   : {'OK' if ok_verif else 'ÉCHEC'}")

    if ok_action and ok_verif:
        resoudre_incident(token, incident_id, f"block_ip {alerte['ip']} + verify OK")
        print(f"  incident #{incident_id} résolu ✅")
    else:
        print(f"  incident #{incident_id} laissé ouvert (action ou vérif en échec)")


# =================================================================================================
# À FAIRE (Léa / Richard) : remplacer cette fonction simulée par la vraie détection.
# Elle doit renvoyer une liste d'alertes (liste vide si rien à signaler).
#
# Piste ML   : scorer les dernières métriques Prometheus ; si score > seuil -> une alerte.
# Piste SIEM : interroger l'API de Loki/Grafana ; si une règle est "firing" -> une alerte.
#
# Format d'une alerte (voir ouvrir_incident) :
#   {"event_type": "...", "severity": "...", "source": "...",
#    "target_service": "backend", "description": "...", "ip": "192.168.137.50"}
# =================================================================================================
_demo_deja_envoyee = False


def detecter_alertes() -> list[dict]:
    """SIMULATION temporaire : renvoie une alerte une seule fois, pour tester la boucle."""
    global _demo_deja_envoyee
    if _demo_deja_envoyee:
        return []
    _demo_deja_envoyee = True
    return [{
        "event_type": "AUTH_FAILURE", "severity": "CRITICAL", "source": "SIEM",
        "target_service": "backend", "ip": "192.168.137.50",
        "description": "SIMULATION : rafale d'échecs de connexion depuis 192.168.137.50",
    }]


def main() -> None:
    print("Moteur de remédiation démarré. Ctrl+C pour arrêter.")
    while True:
        try:
            alertes = detecter_alertes()
            if alertes:
                token = get_token()
                for alerte in alertes:
                    traiter(token, alerte)
        except Exception as exc:  # un cycle en échec ne doit pas arrêter le moteur
            print(f"[ERREUR] {type(exc).__name__}: {exc}")
        time.sleep(INTERVALLE_S)


if __name__ == "__main__":
    main()
