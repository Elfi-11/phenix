#!/usr/bin/env python3
"""Scénario Red Team — Phenix (workshop RESILIENCE-ALPHA).

But : générer une rafale de connexions échouées sur l'API de paiement, pour
déclencher la détection (règle SIEM « rafale d'échecs ») puis la remédiation
automatique (blocage de l'IP). Ce n'est PAS du vol de compte : on envoie
volontairement de mauvais mots de passe pour produire un signal observable.

À lancer UNIQUEMENT depuis le PC attaquant, contre la plateforme fictive de
l'équipe. Toute cible hors de ce laboratoire est interdite par le sujet.

Usage :
    python attaque_login.py                     # valeurs par défaut ci-dessous
    python attaque_login.py --essais 100        # 100 tentatives
    python attaque_login.py --cible http://192.168.137.1:8080 --delai 0.1
"""
import argparse
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Le module 'requests' manque. Installez-le avec :  pip install requests")

# --- Valeurs par défaut (modifiables en haut du fichier ou en argument) --------------------------
CIBLE = "http://192.168.137.1:8080"   # PC hôte sur le point d'accès RESILIENCE-G5
UTILISATEUR = "alice_client"          # compte qui existe (les échecs sont dus au mot de passe)
NB_ESSAIS = 60                        # au-dessus du seuil de la règle SIEM (> 10 / 5 min)
DELAI_S = 0.2                         # pause entre deux tentatives (secondes)


def lancer(cible: str, utilisateur: str, essais: int, delai: float) -> None:
    url = f"{cible.rstrip('/')}/api/auth/login"
    print(f"Cible      : {url}")
    print(f"Utilisateur: {utilisateur}  (mot de passe volontairement faux)")
    print(f"Tentatives : {essais}  |  délai : {delai}s\n")

    codes = {}
    debut = time.time()
    for i in range(1, essais + 1):
        corps = {"username": utilisateur, "password": f"mauvais_mdp_{i}"}
        try:
            reponse = requests.post(url, json=corps, timeout=5)
            code = reponse.status_code
        except requests.RequestException as exc:
            # 403 = l'IP vient d'être bloquée par la remédiation (c'est le résultat attendu !)
            code = f"erreur réseau ({type(exc).__name__})"
        codes[str(code)] = codes.get(str(code), 0) + 1
        print(f"  essai {i:>3}/{essais} -> {code}")
        time.sleep(delai)

    duree = time.time() - debut
    print(f"\nTerminé en {duree:.1f}s. Répartition des réponses :")
    for code, n in sorted(codes.items()):
        print(f"  {code} : {n}")
    print("\nAttendu : des 401 (identifiants invalides), puis des 403 ou erreurs")
    print("réseau quand la remédiation bloque l'IP. Vérifier le dashboard admin.")


def main() -> None:
    p = argparse.ArgumentParser(description="Rafale de connexions échouées (démo détection + remédiation)")
    p.add_argument("--cible", default=CIBLE, help=f"URL de la plateforme (défaut : {CIBLE})")
    p.add_argument("--utilisateur", default=UTILISATEUR, help=f"nom d'utilisateur (défaut : {UTILISATEUR})")
    p.add_argument("--essais", type=int, default=NB_ESSAIS, help=f"nombre de tentatives (défaut : {NB_ESSAIS})")
    p.add_argument("--delai", type=float, default=DELAI_S, help=f"pause entre tentatives en s (défaut : {DELAI_S})")
    args = p.parse_args()

    if args.essais < 1:
        sys.exit("Le nombre de tentatives doit être au moins 1.")
    lancer(args.cible, args.utilisateur, args.essais, args.delai)


if __name__ == "__main__":
    main()
