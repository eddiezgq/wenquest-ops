# WenQuest Ops hub image (docs/plan.md, Phase 1 item 3) with the web workspace (ADR-0007)
# Building in China (ADR-0023): docker build --build-arg NPM_REGISTRY=https://registry.npmmirror.com
#   --build-arg PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple/ --build-arg APT_MIRROR=mirrors.aliyun.com .
# Empty (the default) uses the usual sources.
FROM node:22-slim AS web
ARG NPM_REGISTRY=""
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi && npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ARG PIP_MIRROR=""
ARG APT_MIRROR=""
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WQO_WEB_DIR=/app/web
WORKDIR /app
COPY pyproject.toml README.md ./
COPY wqops/ wqops/
COPY companies/ companies/
COPY --from=web /web/dist/ web/
# Tesseract reads scanned documents in the document library (ADR-0014), Chinese scans with chi-sim (ADR-0023);
# /data/files holds the library's files
RUN if [ -n "$APT_MIRROR" ]; then sed -i "s#deb.debian.org#$APT_MIRROR#g" /etc/apt/sources.list.d/debian.sources; fi \
    && apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir ${PIP_MIRROR:+--index-url "$PIP_MIRROR"} ".[hub]" && useradd -r -u 10001 wqo \
    && mkdir -p /data/files && chown -R wqo /data
ENV WQO_FILES_DIR=/data/files
USER wqo
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/health', timeout=4)" || exit 1
CMD ["uvicorn", "wqops.hub.app:app", "--host", "0.0.0.0", "--port", "8100"]
