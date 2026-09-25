FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ghostscript \
        qpdf \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-ind \
        unpaper \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system kerjapedia \
    && useradd --system --gid kerjapedia kerjapedia \
    && mkdir -p /workspace/storage /workspace/model-cache \
    && chown -R kerjapedia:kerjapedia /workspace

COPY apps/api/requirements-prod.txt apps/api/requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/app ./app
COPY dataset ./dataset
COPY apps/api/start.sh ./
RUN chmod +x start.sh

USER kerjapedia
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"

CMD ["./start.sh"]
