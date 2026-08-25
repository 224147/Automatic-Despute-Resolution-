FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app/ ./app/
COPY scripts/ ./scripts/
RUN pip install --no-cache-dir .

COPY documents/ ./documents/

RUN mkdir -p data/vector_store
RUN mkdir -p data/chroma

COPY alembic.ini ./

RUN mkdir -p data/vector_store
RUN mkdir -p data/chroma

COPY alembic.ini ./
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
