"""ES baglantisi (config'ten host/index)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from elasticsearch import Elasticsearch

from institution_resolver_v3.config import load_config


@lru_cache(maxsize=8)
def get_client(host: str | None = None, request_timeout: int = 300) -> Elasticsearch:
    """(host, timeout) basina TEK `Elasticsearch` nesnesi - baglanti havuzu paylasilir.

    B5 (2026-08-06). ONCEDEN her cagri yeni bir client (dolayisiyla yeni bir
    urllib3 baglanti havuzu) kuruyordu ve `search`/`search_many`/`search_knn`/
    `fetch_embeddings` client gecirmedigi icin bu sorgu basina 11-15 kez
    oluyordu.

    ASIL gerekce HIZ DEGIL, KAYNAK. Olcum (localhost):
      - client kurulumu 0.112 ms, cagri basi fark +0.32 ms -> sorgu basina
        3.5-4.8 ms, yani toplamin ~%1'i. Hiz gerekcesi zayif.
      - AMA soketler birikiyordu: 1 sorgu sonrasi 14 acik TCP, 31 sorgu sonrasi
        194; ancak `gc.collect()` sonrasi 1'e dusuyor. Yani client'lar referans
        dongusu tasidigi icin cop toplayici bir tur atana kadar acik kaliyor.
        Bu makinede `ulimit -n` yuksek, ama Docker/Linux varsayilani genelde
        1024 ve `--workers>1` paralel batch'te birikme hizlanir.

    `lru_cache` anahtari (host, request_timeout): farkli host/timeout ile
    cagirmak AYRI client dondurur - istenen davranis. `elasticsearch-py` client'i
    thread-safe, `csv_runner`'in ThreadPoolExecutor'uyla paylasilmasi guvenli.
    Testlerde yeniden kurmak gerekirse `get_client.cache_clear()`.
    """
    cfg = load_config()
    return Elasticsearch(host or cfg["elasticsearch"]["host"], request_timeout=request_timeout)


def es_config() -> dict[str, Any]:
    return load_config()["elasticsearch"]
