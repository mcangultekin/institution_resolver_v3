#!/usr/bin/env bash
set -e

# Config file default if not set
export INRES3_CONFIG="${INRES3_CONFIG:-/app/config/docker.yaml}"
ES_HOST="${ES_HOST:-http://elasticsearch:9200}"
OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
INDEX_NAME="${INDEX_NAME:-institutions_v1}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:e4b}"

echo "===================================================="
echo "  Institution Resolver v3 - Başlatılıyor"
echo "===================================================="

# 1. Elasticsearch'ün hazır olmasını bekle (timeout: ~150 saniye)
echo ">> Elasticsearch ($ES_HOST) bekleniyor..."
ES_WAIT_TRIES=0
ES_WAIT_MAX=75
until curl -s "$ES_HOST/_cluster/health" | grep -q '"status"'; do
  ES_WAIT_TRIES=$((ES_WAIT_TRIES + 1))
  if [ "$ES_WAIT_TRIES" -ge "$ES_WAIT_MAX" ]; then
    echo ">> HATA: Elasticsearch $((ES_WAIT_MAX * 2)) saniye içinde hazır olmadı, çıkılıyor."
    exit 1
  fi
  sleep 2
done
echo ">> Elasticsearch hazır."

# 2. İndeks kontrolü ve ilk indeksleme (sadece varlık değil, dolu olup olmadığı da kontrol edilir)
DOC_COUNT=0
if curl -sf -o /dev/null "$ES_HOST/$INDEX_NAME"; then
  DOC_COUNT=$(curl -sf "$ES_HOST/$INDEX_NAME/_count" | grep -o '"count":[0-9]*' | grep -o '[0-9]*' || echo 0)
fi

if [ "${DOC_COUNT:-0}" -gt 0 ]; then
  echo ">> Elasticsearch indeksi ($INDEX_NAME) mevcut ve dolu ($DOC_COUNT doküman). İndeksleme adımı atlanıyor."
else
  echo ">> Elasticsearch indeksi ($INDEX_NAME) yok ya da boş."
  echo ">> Otomatik ilk kurulum başlatılıyor (index mapping + veri ve vektör yükleme)..."
  if [ -f "/app/data/processed/parent_canonical.jsonl" ]; then
    inres3 setup-es
    inres3 index --embeddings
    echo ">> İlk indeksleme başarıyla tamamlandı."
  else
    echo ">> UYARI: /app/data/processed/ verileri bulunamadı! İndeksleme yapılamadı."
  fi
fi

# 3. Ollama model kontrolü
echo ">> Ollama kontrol ediliyor ($OLLAMA_HOST)..."
if curl -sf "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
  if curl -sf "$OLLAMA_HOST/api/tags" | grep -q "$OLLAMA_MODEL"; then
    echo ">> Ollama modeli ($OLLAMA_MODEL) mevcut."
  else
    echo ">> Ollama modeli ($OLLAMA_MODEL) indiriliyor (ilk çalıştırmada biraz sürebilir)..."
    curl -s -X POST "$OLLAMA_HOST/api/pull" -d "{\"name\": \"$OLLAMA_MODEL\"}" > /dev/null 2>&1 || true
    echo ">> Ollama modeli hazır."
  fi
fi

echo "===================================================="
echo "  Sistem Hazır! Servis Başlatılıyor..."
echo "===================================================="

exec "$@"
