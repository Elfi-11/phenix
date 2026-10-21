"""Trafic de l'API pour le dashboard : relais en lecture seule vers Prometheus (réservé ADMIN)."""
import json
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.security import require_role

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_role("ADMIN"))])

# Requêtes par seconde sur 1 min glissante (codes regroupés en 2xx/4xx/5xx par l'instrumentation)
QUERIES = {
    "total": "sum(rate(http_requests_total[1m]))",
    "errors": 'sum(rate(http_requests_total{status=~"4xx|5xx"}[1m]))',
}
WINDOW_S = 15 * 60
STEP_S = 15


def _query_range(query: str, start: float, end: float) -> dict[int, float]:
    params = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": STEP_S})
    with urllib.request.urlopen(f"{settings.prometheus_url}/api/v1/query_range?{params}", timeout=3) as res:
        result = json.load(res)["data"]["result"]
    # Aucune série = aucune requête sur la période
    return {int(t): float(v) for t, v in result[0]["values"]} if result else {}


# Points des 15 dernières minutes : [{ "t": secondes Unix, "total": req/s, "errors": req/s }]
@router.get("/traffic")
def traffic():
    end = time.time()
    start = end - WINDOW_S
    try:
        series = {name: _query_range(q, start, end) for name, q in QUERIES.items()}
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Prometheus indisponible") from exc

    timestamps = sorted(set(series["total"]) | set(series["errors"]))
    return [
        {"t": t, "total": series["total"].get(t, 0.0), "errors": series["errors"].get(t, 0.0)}
        for t in timestamps
    ]
