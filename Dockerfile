# Institution Resolver v3 - API servis imaji.
# CPU-only: bu container'da GPU yok (embedding modeli CPU'da calisir, bkz.
# embedding/encoder.py _pick_device fallback'i); torch'un CUDA wheel'ini
# indirmemek icin CPU index'i acikca kullanilir (imaj boyutu + build suresi).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -e ".[llm,embed,api]"

ENV INRES3_CONFIG=/app/config/docker.yaml
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["inres3-serve"]
