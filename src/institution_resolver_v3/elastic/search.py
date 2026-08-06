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

# subunit ESKİ agirliklarla SABİT - parent'taki degisiklik buraya sizmasin (bilerek kapsam disi)
_SUBUNIT_FIELDS = ["name^3", "name.ascii^2", "aliases_text^1.5", "aliases_text.ascii", "parent_name^1.5", "parent_name.ascii"]
# PARENT'in TEK arama kanali (2026-07-29): kanonik ad / alias AYRIMI YOK.
# `name` ve birlesik `aliases_text` parent aramasindan CIKARILDI - ikisi de
# nested `alias_variants` icinde zaten var (kanonik ad kayitlarin %100'unde
# alias listesinde; alias'siz parent yok - ikisi de olculdu).
_PARENT_ALIAS_VARIANT_FIELDS = ["alias_variants.value^2", "alias_variants.value.ascii^1.3"]


def _multi_match(text: str, fields: list[str]) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": text,
            "type": "most_fields",
            "fields": fields,
            "fuzziness": "AUTO",
            "operator": "or",
        }
    }


def _alias_variants_clause(text: str) -> dict[str, Any]:
    """PARENT aramasinin TEK kanali: her yazim ayri nested belge, ORTAK havuz.

    Tasarim karari (kullanici, 2026-07-29): kanonik ad ile alias arasinda ayrim
    YOK. Butun yazimlar tek havuza girer, sorgu hepsine karsi ayni sekilde
    aranir, hangisiyle eslesirse eslessin sonuc KURUMUN KANONIK KAYDI olur
    (nested sorgu zaten parent belgesini dondurur).

    Neden `name`/`aliases_text` cikarildi: ikisi de ayri alan olarak dururken
    kanonik ad her iki kanali birden atesliyor ve skorlar toplaniyordu - yani
    kanonik adin YAPISAL bir ayricaligi vardi. Birlesik `aliases_text` ayrica
    alias sinirlarini kaybediyor: BM25'in alan-uzunlugu normu tek metne bakar,
    boylece cok yazimli kurum sistematik dusuk puan alir. Burada her yazim kendi
    belgesi, kendi uzunluk normu; `score_mode: max` ile kurumu EN IYI yazimi
    temsil eder (alias sayisi ne odul ne ceza).

    GUVENLIK: bu kanal `alias_variants`e TEK BASINA bagimli. Alan yalnizca
    parent belgelerinde ve document.py'de uretiliyor; uretim bozulursa parent
    aramasi komple korlesir. Iki on kosul OLCULDU (2026-07-29, 106.183 parent):
    kanonik ad kayitlarin %100'unde alias listesinde, alias'siz parent 0 tane.
    Kosullar `tests/unit/test_elastic_mapping.py`'de sabitlendi.

    Olculdu (canli index, 200 kurum kendi alias'iyla arandi):
                              alias top1 / top10 / havuz disi | kanonik top1
    name+aliases_text (eski) :  %47.0 / %70.5 / %11.0         | %98.5
    + nested (ara surum)     :  %58.5 / %86.5 /  %1.0         | %99.5
    SADECE nested (bu)       :  %84.5 / %99.5 /  %0.5         | %100.0
    Kanonik ad-alias ucurumu 51.5 -> 15.5 puana indi. Somut vaka: "middle east
    technical university" (ODTU'nun alias'i birebir) eskiden ilk 50'de YOKTU,
    ara surumde 14., bu surumde 1.
    """
    return {
        "nested": {
            "path": "alias_variants",
            "score_mode": "max",
            "query": _multi_match(text, _PARENT_ALIAS_VARIANT_FIELDS),
        }
    }


def build_search_query(
    text: str, record_type: str, *, extra_filters: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Lexical bool sorgusu (ES gerektirmez - testlenebilir).

    `extra_filters`: ek terim filtreleri (ör. parent-first cascade icin
    `{"term": {"parent_id": "..."}}`) - skor'u etkilemez, sadece havuzu daraltir.

    PARENT: tek kanal - nested `alias_variants` (kanonik ad/alias ayrimi YOK,
    bkz. `_alias_variants_clause`). SUBUNIT: eski alanlar ve eski yapi AYNEN
    (bilerek kapsam disi) - parent'taki degisiklik buraya sizmaz.
    """
    filters: list[dict[str, Any]] = [{"term": {"record_type": record_type}}]
    filters.extend(extra_filters or [])
    if record_type == "subunit":
        return {"bool": {"filter": filters, "must": [_multi_match(text, _SUBUNIT_FIELDS)]}}
    return {"bool": {"filter": filters, "must": [_alias_variants_clause(text)]}}


# Arama yanitinda ISTENEN _source alanlari (2026-08-06). Belge 12 alan tasiyor
# ama Python tarafinda yalnizca bunlar okunuyor; gerisi ag/JSON yuku.
#
# NEDEN: `_source` filtresi ARAMAYI ETKILEMEZ - arama ters indekse bakar, `_source`
# yalnizca "bulunan belgeyi geri ver" kismidir. `aliases_text` ve `alias_variants`
# aranmaya aynen devam eder, sadece yanitta geri gonderilmezler.
# OLCUM (parent:143): belge 17.388 B, Python'un okudugu 156 B (%0.9) - kalanin
# neredeyse tamami `embedding` (16.970 B, 768 ondalik sayi JSON metni olarak).
# Sorgu basina 12-16 ES cagrisi x bu yuk = 2.5-7.6 MB/sorgu olculdu.
#
# LISTE TUKETICI TARAMASIYLA cikarildi (tahmin DEGIL) - `_attach_signals` hit
# sozlugunu oldugu gibi `ScoredCandidate.raw`'a koyar ve `raw` su dort yerde
# ad ad okunur:
#   decompose.py    -> name, aliases
#   _attach_signals -> id, record_type, name, aliases
#   gate.py         -> parent_id            (capraz-havuz tutarlilik)
#   resolve.py      -> parent_id            (cascade terms filtresi)
#   candidates.py   -> country, city, parent_id, parent_name, kind_label_raw
# `country`/`city` ozellikle kritik: prompt "ulke/sehir tutarliligi ZORUNLU
# kontroldur" diyor - alan dusseydi hakem o kurali SESSIZCE uygulayamazdi.
# Eksik alan hata vermez, `None` olur; bu yuzden liste comert tutuldu ve
# tests/unit/test_elastic_mapping.py'de sabitlendi.
#
# `embedding` LISTEDE YOK: hicbir karar yolu kosinus kullanmiyor (yalniz CLI/
# API/CSV gosterimi). kNN retrieval etkilenmez - o ES tarafinda calisir, skoru
# yanitla gelir. Havuza girip kNN top-K'ya girmemis adaylarin kosinusu
# `resolve._default_cosine_fn` tarafindan mget ile tamamlanir (embedding artik
# _source'ta gelmedigi icin o yol devreye girer).
POOL_SOURCE_FIELDS = [
    "id",
    "record_type",
    "name",
    "aliases",
    "parent_id",
    "parent_name",
    "country",
    "city",
    "kind_label_raw",
]


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
        source_includes=POOL_SOURCE_FIELDS,  # bkz. POOL_SOURCE_FIELDS notu
    )
    return [{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]


def search_many(
    texts: list[str],
    record_type: str,
    *,
    extra_filters: list[dict[str, Any]] | None = None,
    client: Elasticsearch | None = None,
    index: str | None = None,
    size: int = 50,
) -> list[list[dict[str, Any]]]:
    """`search()`in COKLU-metin hali: tum sorgular TEK `msearch` round-trip'inde.

    Sonuc, `[search(t, ...) for t in texts]` ile BYTE-DENK'tir (ayni analyzer,
    ayni bool sorgu, ayni determinist sort) - fark yalnizca N sirali HTTP yerine
    1 istek olmasi (decompose'un O(n^2) span aramasi icin). Bir alt-sorgu ES
    tarafinda hata verirse (eskiden `search()` exception firlatirdi) o span BOS
    liste olur - decompose'da "o kesimden aday yok" demektir, digerleri etkilenmez.
    """
    if not texts:
        return []
    client = client or get_client()
    index = index or es_config()["index"]
    query = build_search_query  # yerel ad - loop'ta ad aramasi olmasin
    body: list[dict[str, Any]] = []
    for text in texts:
        body.append({"index": index})
        body.append(
            {
                "size": size,
                "query": query(expand_query_text(text), record_type, extra_filters=extra_filters),
                "sort": [{"_score": {"order": "desc"}}, {"id": {"order": "asc"}}],
                "_source": POOL_SOURCE_FIELDS,  # bkz. POOL_SOURCE_FIELDS notu
            }
        )
    resp = client.msearch(body=body)
    out: list[list[dict[str, Any]]] = []
    for r in resp["responses"]:
        if r.get("error") or "hits" not in r:
            out.append([])
            continue
        out.append([{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in r["hits"]["hits"]])
    return out


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
        source_includes=POOL_SOURCE_FIELDS,  # bkz. POOL_SOURCE_FIELDS notu
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
