FROM python:3.10-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client libmagic1 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser backend/ .

USER appuser

EXPOSE 8000

# create_db est lancé comme module pour que `from app...` fonctionne
CMD ["bash", "-c", "python -m app.scripts.create_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
