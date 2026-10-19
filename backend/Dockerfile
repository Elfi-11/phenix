FROM python:3.10-slim-bookworm

RUN apt update && apt install -y postgresql-client libmagic1 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./backend/app/scripts /app/scripts
COPY backend/ .

RUN pip install -e . && rm -rf /root/.cache /tmp/*

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["bash", "-c", "python /app/scripts/create_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]