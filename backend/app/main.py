from fastapi import APIRouter, FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import accounts, assistant, attackme, auth, incidents, metrics, selftest, transactions

app = FastAPI(title="Phenix API")

# Toutes les routes métier passent par /api (c'est ce que Nginx transmet au backend)
api = APIRouter(prefix="/api")


@app.get("/health")
def health():
    """Utilisé par le healthcheck Docker et par Nginx (/health)."""
    return {"status": "ok"}


@api.get("/ping")
def ping():
    return {"pong": True}


api.include_router(auth.router)
api.include_router(transactions.router)
api.include_router(accounts.router)
api.include_router(incidents.router)
api.include_router(metrics.router)
api.include_router(assistant.router)
api.include_router(selftest.router)
# Faille volontaire (injection SQL) pour la démonstration : retirer cette ligne pour la désactiver
api.include_router(attackme.router)

app.include_router(api)

# Métriques Prometheus (requêtes, codes HTTP, latences) sur /metrics.
# Non exposé publiquement : Nginx ne transmet que /api, /docs et /health.
Instrumentator(excluded_handlers=["/health", "/metrics"]).instrument(app).expose(app, include_in_schema=False)
