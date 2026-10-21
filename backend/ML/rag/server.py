"""Serveur HTTP minimal de l'assistant : POST /ask {"question": "..."} -> résultat de answer().

Bibliothèque standard uniquement. Joignable seulement par le backend (réseau Docker "assistant").
Un seul thread : les questions sont traitées l'une après l'autre (le modèle occupe déjà le CPU).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from rag.assistant import answer
from rag.config import Config

PORT = 8000
MAX_BODY = 10_000  # octets


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, {"status": "error", "message": "Route inconnue"})

        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_BODY:
            return self._send(400, {"status": "error", "message": "Corps de requête absent ou trop long"})

        try:
            question = json.loads(self.rfile.read(length))["question"]
            if not isinstance(question, str):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"status": "error", "message": 'JSON attendu : {"question": "..."}'})

        try:
            return self._send(200, answer(Config(), question))
        except ValueError as exc:
            # Messages de validation du RAG (question vide, index absent...) : sûrs à afficher
            return self._send(400, {"status": "error", "message": str(exc)})
        except Exception as exc:
            # Comme la CLI : pas de réponse brute d'Ollama renvoyée au client
            print(f"Erreur assistant : {type(exc).__name__}", file=sys.stderr)
            return self._send(500, {"status": "error", "message": "Vérifier Ollama, les modèles et l'index"})


if __name__ == "__main__":
    print(f"Assistant RAG en écoute sur le port {PORT}", file=sys.stderr)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
