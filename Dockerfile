FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY teleguard teleguard
COPY api api
COPY datagen datagen
COPY pipelines pipelines
COPY db db
COPY docker docker

RUN pip install --no-cache-dir -r requirements.txt -e . \
    && chmod +x /app/docker/bootstrap_demo.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
