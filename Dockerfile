# Python
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg/ffprobe required for reel assembly
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY content ./content
COPY scripts ./scripts
COPY run.py .

RUN mkdir -p /app/storage

# Render injects PORT; default 4100 for local docker runs
ENV PORT=4100 \
    NODE_ENV=production \
    DATABASE_PATH=/app/storage/manifestia.db \
    STORAGE_ROOT=/app/storage

EXPOSE 4100

# Single worker: SQLite + in-process background reel jobs
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-4100} --workers 1"]
