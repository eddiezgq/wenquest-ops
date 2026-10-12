# WenQuest Ops hub image (docs/plan.md, Phase 1 item 3)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY wqops/ wqops/
COPY companies/ companies/
RUN pip install --no-cache-dir ".[hub]" && useradd -r -u 10001 wqo
USER wqo
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/health', timeout=4)" || exit 1
CMD ["uvicorn", "wqops.hub.app:app", "--host", "0.0.0.0", "--port", "8100"]
