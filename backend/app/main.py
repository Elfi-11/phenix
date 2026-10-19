from fastapi import APIRouter, FastAPI

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


app.include_router(api)
