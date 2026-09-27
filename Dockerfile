# AutoDiagnose AI backend — FastAPI + Chroma + Claude on Bedrock
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROMA_DIR=/app/var/chroma \
    SQLITE_PATH=/app/var/autodiagnose.db

WORKDIR /app
RUN useradd --create-home app && mkdir -p /app/var && chown app /app/var

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY data/zenodo ./data/zenodo

# Run as a non-root user; runtime data (Chroma index, SQLite) lives on the volume at /app/var.
USER app
# Bake the embedding model into the image so the first request isn't slow.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm up'])"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
