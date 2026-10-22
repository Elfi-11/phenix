"""Paiement réel aller-retour : contrôle périodique et preuve fraîche demandée par Ansible."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from payment_probe import PaymentProbe

# Le test passe par l’entrée Caddy de Docker Desktop, donc WAF puis Nginx.
# Sur un autre environnement, définir explicitement une entrée équivalente.
API = os.getenv('SELFTEST_API', 'http://host.docker.internal:8080')
USER = os.getenv('SELFTEST_USER', 'selftest_client')
RECEIVER = os.getenv('SELFTEST_RECEIVER_USER', 'marchand_beta')
PASSWORD = os.getenv('DEMO_USER_PASSWORD', '')
INTERVAL_S = max(1, int(os.getenv('SELFTEST_INTERVAL', '10')))
STATE_PATH = os.getenv('SELFTEST_STATE_PATH', '/app/selftest_state/payment-probe.json')
STATUS_PORT = 9000
_etat = {'ok': None, 'http_status': None, 'at': None, 'detail': 'démarrage…'}
_status_lock = threading.Lock()
_probe = None


def un_paiement(require_fresh=False):
    # Tous les appels passent par le même objet et le même verrou ; le test
    # périodique ne peut pas interférer avec le test lancé par Ansible.
    result = _probe.run(require_fresh=require_fresh)
    with _status_lock:
        _etat.clear()
        _etat.update(result)
    print(f"selftest: {'OK' if result['ok'] else 'ECHEC'} — {result['detail']}", flush=True)
    return result


def boucle():
    while True:
        un_paiement()
        time.sleep(INTERVAL_S)


class StatusHandler(BaseHTTPRequestHandler):
    def respond(self, code, body):
        encoded = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        # Format historique conservé pour le backend et le dashboard.
        if self.path != '/status':
            self.respond(404, {'detail': 'Route inconnue'}); return
        with _status_lock:
            body = dict(_etat)
        self.respond(200, body)

    def do_POST(self):
        # Déclenchement uniquement depuis l’intérieur du conteneur via docker exec.
        # Aucun accès ADMIN ou SERVICE supplémentaire n’est accordé à l’API métier.
        if self.path != '/run':
            self.respond(404, {'detail': 'Route inconnue'}); return
        if self.client_address[0] not in ('127.0.0.1', '::1'):
            self.respond(403, {'detail': 'Déclenchement local uniquement'}); return
        result = un_paiement(require_fresh=True)
        self.respond(200 if result['ok'] else 503, result)

    def log_message(self, *args):
        pass


def verify_once():
    # Ansible exige un paiement commencé APRES sa demande, pas le dernier vert
    # du dashboard. Le serveur exécute un nouveau cycle et renvoie les références.
    request = urllib.request.Request(f'http://127.0.0.1:{STATUS_PORT}/run', method='POST')
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            print(exc.read().decode(), flush=True)
        except Exception:
            print('Échec du test métier', flush=True)
        return 1
    except (urllib.error.URLError, OSError, ValueError):
        print('Selftest indisponible ou réponse invalide', flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get('ok') is True else 1


def main():
    global _probe
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Demander un test neuf au serveur déjà lancé')
    args = parser.parse_args()
    if args.verify:
        return verify_once()
    # Le service échoue explicitement si le volume persistant manque ou si une
    # autre instance utilise le même journal. Aucun repli silencieux dans /tmp.
    state = Path(STATE_PATH)
    state.parent.mkdir(parents=True, exist_ok=True)
    owner = open(state.with_suffix('.lock'), 'a+')
    import fcntl
    fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    _probe = PaymentProbe(API, (USER, RECEIVER),
        (os.getenv('SELFTEST_USER_PASSWORD', PASSWORD), os.getenv('SELFTEST_RECEIVER_PASSWORD', PASSWORD)), state)
    server = ThreadingHTTPServer(('0.0.0.0', STATUS_PORT), StatusHandler)
    threading.Thread(target=boucle, daemon=True).start()
    print(f'selftest: aller-retour via {API}, intervalle {INTERVAL_S}s', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        owner.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
