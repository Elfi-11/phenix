"""Contrôle de connectivité : Ollama joignable et deux sorties TCP bloquées.

Test ponctuel complémentaire à l'inspection des réseaux Docker ; il ne démontre
pas à lui seul l'absence de toutes les possibilités de sortie.
"""
import argparse
import json
import socket
import sys
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://ollama:11434')
args = parser.parse_args()
# Ne pas utiliser de proxy HTTP du système pour le contrôle local.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(args.base_url.rstrip('/') + '/api/tags', timeout=5) as response:
        models = json.load(response)
    print('OK : serveur Ollama local joignable')
    print('Modèles :', ', '.join(m['name'] for m in models.get('models', [])))
except Exception as exc:
    print(f'ECHEC : Ollama local inaccessible ({type(exc).__name__})')
    sys.exit(1)

unexpected = False
for address in ['1.1.1.1', '8.8.8.8']:
    try:
        with socket.create_connection((address, 443), timeout=3):
            print(f'ECHEC : connexion externe possible vers {address}:443')
            unexpected = True
    except OSError as exc:
        print(f'Connexion externe impossible vers {address}:443 ({type(exc).__name__})')
if unexpected:
    sys.exit(1)
print('Contrôles ponctuels réussis ; vérifier aussi Internal=true et les réseaux attachés.')
