# WenQuest Ops hub image (docs/plan.md, Phase 1 item 3) with the web workspace (ADR-0007)
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WQO_WEB_DIR=/app/web
WORKDIR /app
COPY pyproject.toml README.md ./
COPY wqops/ wqops/
COPY companies/ companies/
COPY --from=web /web/dist/ web/
# Tesseract reads scanned documents in the document library (ADR-0014); /data/files holds the library's files
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir ".[hub]" && useradd -r -u 10001 wqo \
    && mkdir -p /data/files && chown -R wqo /data
ENV WQO_FILES_DIR=/data/files
USER wqo
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/health', timeout=4)" || exit 1
CMD ["uvicorn", "wqops.hub.app:app", "--host", "0.0.0.0", "--port", "8100"]
