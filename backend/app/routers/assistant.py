"""Relais vers l'assistant RAG (réservé ADMIN) : le RAG n'est jamais exposé directement."""
import json
import socket
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.security import require_role

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_role("ADMIN"))])

# Le modèle tourne sur CPU : nginx laisse 180 s à cette route, on coupe un peu avant
RAG_TIMEOUT_S = 170


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)


# Pose une question à l'assistant ; renvoie { status, answer, sources }
@router.post("/ask")
def ask(data: AssistantQuestion):
    req = urllib.request.Request(
        f"{settings.rag_url}/ask",
        data=json.dumps({"question": data.question}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=RAG_TIMEOUT_S) as res:
            result = json.load(res)
    except (TimeoutError, socket.timeout) as exc:
        raise HTTPException(status_code=504, detail="L'assistant n'a pas répondu à temps") from exc
    except urllib.error.HTTPError as exc:
        # Erreur renvoyée par le RAG (ex. Ollama ou modèles absents) : pas de détail brut au client
        raise HTTPException(status_code=502, detail="L'assistant a rencontré une erreur") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Assistant indisponible") from exc

    # On ne renvoie que les champs attendus par le dashboard
    return {
        "status": result.get("status"),
        "answer": result.get("answer"),
        "sources": result.get("sources", []),
    }
