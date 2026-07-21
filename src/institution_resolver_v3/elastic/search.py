"""Hibrit arama - F1: lexical-only (BM25 + fuzzy), `record_type` filtresiyle.

Tek korpus + `term:{record_type}` filtresi (v2'nin iki-index IDF zehirlenmesi
cozulur). Subunit aramasinda `parent_name` da alanlara girer -> "gazi istatistik"
dogru universitenin istatistigini bulur.

kNN/embedding (anlam eslesmesi) F3'te eklenecek; bu modul o zaman genisler.
Sorgu metni expand_query_text ile hazirlanir (kisaltma genisletme + gorunmez
karakter temizligi; case/aksan KORUNUR - folding'i ES analyzer yapar).
"""

from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from institution_resolver_v3.elastic.client import es_config, get_client
from institution_resolver_v3.normalize.query_pipeline import expand_query_text

_PARENT_FIELDS = ["name^3", "name.ascii^2", "aliases_text^1.5", "aliases_text.ascii"]
_SUBUNIT_FIELDS = _PARENT_FIELDS + ["parent_name^1.5", "parent_name.ascii"]


def build_search_query(text: str, record_type: str) -> dict[str, Any]:
    """Lexical bool sorgusu (ES gerektirmez - testlenebilir)."""
    fields = _SUBUNIT_FIELDS if record_type == "subunit" else _PARENT_FIELDS
    return {
        "bool": {
            "filter": [{"term": {"record_type": record_type}}],
            "must": [
                {
                    "multi_match": {
                        "query": text,
                        "type": "most_fields",
                        "fields": fields,
                        "fuzziness": "AUTO",
                        "operator": "or",
                    }
                }
            ],
        }
    }


def search(
    text: str,
    record_type: str,
    *,
    client: Elasticsearch | None = None,
    index: str | None = None,
    size: int = 50,
) -> list[dict[str, Any]]:
    """`record_type` havuzunu dondurur (skorla, determinist siralamayla)."""
    client = client or get_client()
    index = index or es_config()["index"]
    prepared = expand_query_text(text)
    resp = client.search(
        index=index,
        size=size,
        query=build_search_query(prepared, record_type),
        sort=[{"_score": {"order": "desc"}}, {"id": {"order": "asc"}}],  # determinizm
    )
    hits: list[dict[str, Any]] = []
    for h in resp["hits"]["hits"]:
        hits.append({"id": h["_id"], "score": h["_score"], **h["_source"]})
    return hits
