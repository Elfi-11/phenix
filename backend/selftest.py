"""Transaction de test automatique — preuve de reprise (Axe 1).

Toutes les N secondes, tente un vrai paiement (selftest_client -> marchand).
C'est une vérification ACTIVE du métier : si ce paiement passe, l'API, la base,
l'authentification et la logique de paiement fonctionnent réellement.

Expose le dernier résultat sur http://selftest:9000/status (lu par le backend,
qui le relaie au dashboard admin). Librairie standard uniquement (urllib).
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

API = os.getenv("SELFTEST_API", "http://backend:8000")
USER = os.getenv("SELFTEST_USER", "selftest_client")
PASSWORD = os.getenv("DEMO_USER_PASSWORD", "")
MERCHANT_ID = int(os.getenv("SELFTEST_MERCHANT_ID", "3"))
INTERVAL_S = int(os.getenv("SELFTEST_INTERVAL", "10"))
STATUS_PORT = 9000

# Dernier résultat, partagé entre le thread de test et le serveur de statut
_etat = {"ok": None, "http_status": None, "at": None, "detail": "démarrage…"}
_lock = threading.Lock()


def _post(url: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
    """POST JSON avec urllib. Renvoie (code HTTP, corps décodé)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except Exception:
            return exc.code, {}


def un_paiement() -> dict:
    """Login puis paiement de 1 €. Renvoie le résultat sans lever d'exception."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        code, corps = _post(f"{API}/api/auth/login", {"username": USER, "password": PASSWORD})
        if code != 200:
            return {"ok": False, "http_status": code, "at": now, "detail": "login échoué"}
        token = corps["access_token"]

        # Clé unique par essai : chaque paiement est distinct (pas d'idempotence ici)
        cle = f"selftest-{int(time.time() * 1000)}"
        code, corps = _post(
            f"{API}/api/transactions",
            {"idempotency_key": cle, "receiver_account_id": MERCHANT_ID, "amount": "1.00"},
            token,
        )
        if code in (200, 201):
            return {"ok": True, "http_status": code, "at": now, "detail": "paiement OK"}
        return {"ok": False, "http_status": code, "at": now, "detail": str(corps.get("detail", "paiement refusé"))}
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        # Service injoignable (ex. pendant l'incident) : c'est le ❌ attendu
        return {"ok": False, "http_status": None, "at": now, "detail": f"injoignable ({type(exc).__name__})"}


def boucle():
    while True:
        resultat = un_paiement()
        with _lock:
            _etat.update(resultat)
        print(f"selftest: {'OK' if resultat['ok'] else 'ECHEC'} — {resultat['detail']}", flush=True)
        time.sleep(INTERVAL_S)


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/status":
            self.send_response(404)
            self.end_headers()
            return
        with _lock:
            body = json.dumps(_etat).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # pas de log pour chaque lecture du dashboard


if __name__ == "__main__":
    threading.Thread(target=boucle, daemon=True).start()
    print(f"selftest: statut sur le port {STATUS_PORT}, paiement toutes les {INTERVAL_S}s", flush=True)
    HTTPServer(("0.0.0.0", STATUS_PORT), StatusHandler).serve_forever()
