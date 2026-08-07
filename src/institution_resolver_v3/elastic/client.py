"""ES baglantisi (config'ten host/index)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from elasticsearch import Elasticsearch

from institution_resolver_v3.config import load_config


@lru_cache(maxsize=8)
def get_client(host: str | None = None, request_timeout: int = 300) -> Elasticsearch:
    """(host, timeout) basina TEK `Elasticsearch` nesnesi - baglanti havuzu paylasilir.

    Gerekce HIZ DEGIL, KAYNAK. Eskiden her cagri yeni bir client (dolayisiyla yeni
    bir urllib3 baglanti havuzu) kuruyordu; `search`/`search_many`/`search_knn`/
    `fetch_documents`/`fetch_embeddings` client gecirmedigi icin bu sorgu basina
    10+ kez oluyordu.

    OLCULDU (2026-08-07, bu makine, canli ES): acik TCP soketi cagri sayisiyla
    DOGRUSAL birikiyor - 41 cagri -> 41 soket; `gc.collect()` sonrasi 0'a
    dusuyor, yani client'lar referans dongusu tasidigi icin cop toplayici bir
    tur atana kadar acik kaliyor. Bu makinede `ulimit -n` yuksek oldugu icin
    zarar gorunmuyordu; Docker/Linux varsayilani genelde 1024 ve `--workers>1`
    paralel batch'te birikme hizlanir.

    `lru_cache` anahtari (host, request_timeout): farkli host/timeout ile
    cagirmak AYRI client dondurur - istenen davranis. `elasticsearch-py` client'i
    thread-safe, `csv_runner`'in ThreadPoolExecutor'uyla paylasilmasi guvenli.
    Testlerde/konfig degisiminde yeniden kurmak icin `get_client.cache_clear()`.
    """
    cfg = load_config()
    return Elasticsearch(host or cfg["elasticsearch"]["host"], request_timeout=request_timeout)


def es_config() -> dict[str, Any]:
    return load_config()["elasticsearch"]
