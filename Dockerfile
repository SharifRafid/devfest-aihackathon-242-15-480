# Second Thought - one container: FastAPI scorer (live model) + built React demo.
# Models and synthetic data are committed under ml/models and data/out, so no training at build time.

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY api/ api/
COPY ml/ ml/
COPY data/generate.py data/ASSUMPTIONS.md data/
COPY data/out/ data/out/
COPY --from=web /web/dist web/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"
CMD ["uvicorn", "api.serve:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
