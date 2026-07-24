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

_PARENT_FIELDS = ["name^2.2", "name.ascii^1.5", "aliases_text^2", "aliases_text.ascii^1.3"]
# subunit ESKİ agirliklarla SABİT - parent'taki degisiklik buraya sizmasin (bilerek kapsam disi)
_SUBUNIT_FIELDS = ["name^3", "name.ascii^2", "aliases_text^1.5", "aliases_text.ascii", "parent_name^1.5", "parent_name.ascii"]


def build_search_query(
    text: str, record_type: str, *, extra_filters: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Lexical bool sorgusu (ES gerektirmez - testlenebilir).

    `extra_filters`: ek terim filtreleri (ör. parent-first cascade icin
    `{"term": {"parent_id": "..."}}`) - skor'u etkilemez, sadece havuzu daraltir.
    """
    fields = _SUBUNIT_FIELDS if record_type == "subunit" else _PARENT_FIELDS
    filters: list[dict[str, Any]] = [{"term": {"record_type": record_type}}]
    filters.extend(extra_filters or [])
    return {
        "bool": {
            "filter": filters,
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
    extra_filters: list[dict[str, Any]] | None = None,
    client: Elasticsearch | None = None,
    index: str | None = None,
    size: int = 50,
) -> list[dict[str, Any]]:
    """Lexical (BM25+fuzzy) havuz - `record_type` filtreli, determinist siralama."""
    client = client or get_client()
    index = index or es_config()["index"]
    prepared = expand_query_text(text)
    resp = client.search(
        index=index,
        size=size,
        query=build_search_query(prepared, record_type, extra_filters=extra_filters),
        sort=[{"_score": {"order": "desc"}}, {"id": {"order": "asc"}}],  # determinizm
    )
    return [{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]


# --------------------------------------------------------------------------- #
# Hibrit: BM25 + kNN, RRF ile havuzlanir (RRF SADECE havuzlama - v3 karari)
# --------------------------------------------------------------------------- #
def build_knn_query(
    query_vector: list[float],
    record_type: str,
    *,
    k: int,
    num_candidates: int,
    extra_filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """kNN blogu (record_type filtreli) - ES gerektirmez, testlenebilir."""
    filters: list[dict[str, Any]] = [{"term": {"record_type": record_type}}]
    filters.extend(extra_filters or [])
    knn_filter = filters[0] if len(filters) == 1 else {"bool": {"filter": filters}}
    return {
        "field": "embedding",
        "query_vector": query_vector,
        "k": k,
        "num_candidates": num_candidates,
        "filter": knn_filter,
    }


def search_knn(
    text: str,
    record_type: str,
    *,
    extra_filters: list[dict[str, Any]] | None = None,
    client: Elasticsearch | None = None,
    index: str | None = None,
    size: int = 50,
) -> list[dict[str, Any]]:
    """Ham kNN (embedding) havuzu - `search()`in kNN karsiligi, RRF'den ONCE ham skor icin."""
    from institution_resolver_v3.embedding.query_encoder import encode_query

    client = client or get_client()
    index = index or es_config()["index"]
    qvec = encode_query(text).tolist()
    resp = client.search(
        index=index,
        size=size,
        knn=build_knn_query(
            qvec, record_type, k=size, num_candidates=max(100, size * 2), extra_filters=extra_filters
        ),
    )
    return [{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]


def fetch_embeddings(
    doc_ids: list[str],
    *,
    client: Elasticsearch | None = None,
    index: str | None = None,
) -> dict[str, list[float]]:
    """Belge `_id`'lerinden ("record_type:id") embedding vektorlerini ceker (mget).

    Doner: {raw id -> vektor}. Bulunamayan/embeddingsiz belgeler atlanir.
    Kullanim: havuza arama sonucu olarak DEGIL enjeksiyonla girmis adaylarin
    (raw'inda embedding tasimayan) kosinusunu doldurmak (bkz. retrieve/resolve.py).
    """
    if not doc_ids:
        return {}
    client = client or get_client()
    index = index or es_config()["index"]
    resp = client.mget(index=index, ids=doc_ids, source_includes=["id", "embedding"])
    out: dict[str, list[float]] = {}
    for d in resp["docs"]:
        if d.get("found") and d["_source"].get("embedding"):
            out[d["_source"]["id"]] = d["_source"]["embedding"]
    return out


def rrf_merge(
    rank_lists: list[list[dict[str, Any]]], *, k: int = 60, size: int = 50
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion: birden fazla sirali listeyi tek havuza birlestirir.

    skor(id) = Σ 1/(k + rank). Belge kaynagi ilk gorulen listeden alinir.
    Determinist: skor desc, sonra id asc.
    """
    scores: dict[str, float] = {}
    source: dict[str, dict[str, Any]] = {}
    for lst in rank_lists:
        for rank, hit in enumerate(lst):
            hid = hit["id"]
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (k + rank + 1)
            source.setdefault(hid, hit)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], _id_key(kv[0])))
    out: list[dict[str, Any]] = []
    for hid, s in ordered[:size]:
        out.append({**source[hid], "rrf_score": s})
    return out


def _id_key(x: str):
    return int(x) if x.isdigit() else x


def search_hybrid(
    text: str,
    record_type: str,
    *,
    extra_filters: list[dict[str, Any]] | None = None,
    client: Elasticsearch | None = None,
    index: str | None = None,
    size: int = 50,
) -> list[dict[str, Any]]:
    """BM25 + kNN havuzlarini RRF ile birlestirir. Sorgu vektoru e5 ile kodlanir."""
    client = client or get_client()
    index = index or es_config()["index"]

    bm25 = search(text, record_type, extra_filters=extra_filters, client=client, index=index, size=size)
    knn = search_knn(text, record_type, extra_filters=extra_filters, client=client, index=index, size=size)

    return rrf_merge([bm25, knn], size=size)
