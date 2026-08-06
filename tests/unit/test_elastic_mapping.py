"""ES mapping + belge kurucu - ES gerektirmeyen yapisal testler."""

from __future__ import annotations

from institution_resolver_v3.elastic.document import (
    build_document,
    build_parent_name_index,
)
from institution_resolver_v3.elastic.mappings import (
    EMBEDDING_DIM,
    build_index_body,
    build_mapping,
)


def test_mapping_has_record_type_and_single_index_fields() -> None:
    props = build_mapping()["properties"]
    assert props["record_type"] == {"type": "keyword"}       # tek-index filtre alani
    assert props["name"]["type"] == "text"
    # name alt alanlari: ascii + edge + keyword
    assert set(props["name"]["fields"]) == {"ascii", "edge", "keyword"}
    assert props["normalized_name"] == {"type": "keyword"}   # tam-eslesme kanali


def test_mapping_reserves_dense_vector_768() -> None:
    emb = build_mapping()["properties"]["embedding"]
    assert emb["type"] == "dense_vector"
    assert emb["dims"] == EMBEDDING_DIM == 768
    assert emb["similarity"] == "cosine"


def test_index_body_has_turkish_analyzers() -> None:
    analyzers = build_index_body()["settings"]["analysis"]["analyzer"]
    assert {"turkish_analyzer", "ascii_analyzer", "edge_analyzer"} <= set(analyzers)
    # Turkce-dogru kucuk harf filtresi (I/i tuzagi ES tarafinda)
    filters = build_index_body()["settings"]["analysis"]["filter"]
    assert filters["turkish_lowercase"] == {"type": "lowercase", "language": "turkish"}


def test_build_document_injects_parent_name_into_subunit() -> None:
    parents = [{"id": "101", "name": "GAZİ ÜNİVERSİTESİ", "record_type": "parent"}]
    idx = build_parent_name_index(parents)
    sub = {
        "id": "5", "record_type": "subunit", "parent_id": "101",
        "name": "İSTATİSTİK BÖLÜMÜ", "normalized_name": "istatistik bolumu",
        "merged_ids": ["5"], "kind_label_raw": "Bölüm", "unit_type": "bolum",
        "aliases": [{"value": "İSTATİSTİK BÖLÜMÜ", "locale": "tr", "source": "legacy_row"},
                    {"value": "DEPARTMENT OF STATISTICS", "locale": "en", "source": "yok"}],
    }
    doc = build_document(sub, idx)
    assert doc["parent_name"] == "GAZİ ÜNİVERSİTESİ"          # ENJEKSIYON
    assert doc["record_type"] == "subunit"
    assert doc["unit_type"] == "bolum"
    assert "DEPARTMENT OF STATISTICS" in doc["aliases_text"]  # tum alias'lar aramada
    assert doc["merged_ids"] == ["5"]


def test_build_document_parent_has_no_parent_name() -> None:
    p = {"id": "101", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ",
         "normalized_name": "gazi universitesi", "country": "TR",
         "aliases": [{"value": "GAZI UNIVERSITY", "locale": "en", "source": "ror"}]}
    doc = build_document(p, {})
    assert doc["record_type"] == "parent"
    assert "parent_name" not in doc
    assert doc["country"] == "TR"
    assert "GAZI UNIVERSITY" in doc["aliases_text"]


def test_build_document_dedups_alias_values() -> None:
    p = {"id": "1", "record_type": "parent", "name": "X", "normalized_name": "x",
         "aliases": [{"value": "X ÜNİ", "locale": "tr", "source": "a"},
                     {"value": "X ÜNİ", "locale": "tr", "source": "b"}]}
    doc = build_document(p, {})
    assert doc["aliases_text"] == "X ÜNİ"                     # tekrar tek


# --------------------------------------------------------------------------- #
# search query kurucu (ES gerektirmez)
# --------------------------------------------------------------------------- #
from institution_resolver_v3.elastic.search import build_search_query


def _parent_nested(q: dict) -> dict:
    """parent sorgusunun TEK kanali: nested alias_variants."""
    return q["bool"]["must"][0]["nested"]


def test_search_query_filters_record_type() -> None:
    q = build_search_query("gazi universitesi", "parent")
    assert q["bool"]["filter"] == [{"term": {"record_type": "parent"}}]
    assert _parent_nested(q)["query"]["multi_match"]["fuzziness"] == "AUTO"


def test_subunit_query_includes_parent_name_field() -> None:
    q = build_search_query("istatistik", "subunit")
    fields = q["bool"]["must"][0]["multi_match"]["fields"]
    assert any(f.startswith("parent_name") for f in fields)   # parent enjeksiyonu aramada
    # parent aramasinda parent_name YOK
    parent_fields = _parent_nested(build_search_query("gazi", "parent"))["query"]["multi_match"]["fields"]
    assert not any(f.startswith("parent_name") for f in parent_fields)


# --------------------------------------------------------------------------- #
# PARENT: kanonik ad / alias ayrimi YOK - butun yazimlar tek ortak havuzda.
# Olculdu (200 kurum, canli index): alias top1 %47.0 -> %84.5, kanonik %100,
# aradaki ucurum 51.5 -> 15.5 puan.
# --------------------------------------------------------------------------- #
def test_parent_query_searches_each_alias_separately() -> None:
    nested = _parent_nested(build_search_query("gazi university", "parent"))
    assert nested["path"] == "alias_variants"
    assert nested["score_mode"] == "max"        # alias sayisi ne odul ne ceza
    assert nested["query"]["multi_match"]["fields"] == [
        "alias_variants.value^2",
        "alias_variants.value.ascii^1.3",
    ]


def test_parent_query_has_no_separate_name_or_aliases_text_channel() -> None:
    """Ayrim YOK: `name` ve birlesik `aliases_text` parent aramasindan CIKARILDI.

    Ikisi de ayri kanal olarak dururken kanonik ad her iki kanali birden
    atesleyip skor topluyordu - yapisal ayricalik. Yazimlarin tamami zaten
    `alias_variants` icinde (bkz. asagidaki on kosul testleri).
    """
    q = build_search_query("gazi", "parent")
    assert len(q["bool"]["must"]) == 1                     # tek kanal
    assert "should" not in q["bool"]
    metin = str(q)
    assert "aliases_text" not in metin
    assert "name^" not in metin and "name.ascii" not in metin


def test_subunit_query_unchanged_by_parent_alias_channel() -> None:
    """Subunit kapsam disi: eski alanlar, eski yapi, nested kanal YOK."""
    q = build_search_query("istatistik bolumu", "subunit")
    assert "should" not in q["bool"]
    assert len(q["bool"]["must"]) == 1
    assert "nested" not in str(q)
    assert q["bool"]["must"][0]["multi_match"]["fields"] == [
        "name^3", "name.ascii^2", "aliases_text^1.5", "aliases_text.ascii",
        "parent_name^1.5", "parent_name.ascii",
    ]


# --------------------------------------------------------------------------- #
# D varyantinin ON KOSULLARI - parent aramasi artik SADECE `alias_variants`e
# bagimli. Bu iki kosul bozulursa parent aramasi sessizce korlesir, o yuzden
# testle sabitlendi (ikisi de 106.183 parent uzerinde olculdu: %100 ve 0).
# --------------------------------------------------------------------------- #
def test_parent_alias_variants_always_contains_canonical_name() -> None:
    """Kanonik ad, alias listesinde de bulundugu icin nested havuza girer."""
    p = {"id": "1", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ",
         "normalized_name": "gazi universitesi",
         "aliases": [{"value": "GAZİ ÜNİVERSİTESİ", "locale": "tr", "source": "legacy_row"},
                     {"value": "GAZI UNIVERSITY", "locale": "en", "source": "ror"}]}
    doc = build_document(p, {})
    assert {"value": "GAZİ ÜNİVERSİTESİ"} in doc["alias_variants"]


def test_parent_without_aliases_is_unsearchable_and_must_not_happen() -> None:
    """Alias'siz parent ARANAMAZ hale gelir - kanonik veride boyle kayit YOK.

    Bu test davranisi 'dogru' diye sabitlemiyor; tehlikeyi gorunur kiliyor.
    Ingest bir gun alias'siz parent uretirse arama sessizce degil, burada patlar.
    """
    p = {"id": "9", "record_type": "parent", "name": "X", "normalized_name": "x",
         "aliases": []}
    doc = build_document(p, {})
    assert doc["alias_variants"] == []      # -> nested sorgu bu kaydi ASLA bulamaz


def test_parent_document_has_one_nested_doc_per_alias() -> None:
    p = {"id": "101", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ",
         "normalized_name": "gazi universitesi",
         "aliases": [{"value": "GAZI UNIVERSITY", "locale": "en", "source": "ror"},
                     {"value": "GÜ", "locale": "tr", "source": "legacy"}]}
    doc = build_document(p, {})
    assert doc["alias_variants"] == [{"value": "GAZI UNIVERSITY"}, {"value": "GÜ"}]
    assert "GAZI UNIVERSITY" in doc["aliases_text"]            # birlesik kanal da duruyor


def test_subunit_document_has_no_alias_variants() -> None:
    parents = [{"id": "101", "name": "GAZİ ÜNİVERSİTESİ", "record_type": "parent"}]
    sub = {"id": "5", "record_type": "subunit", "parent_id": "101",
           "name": "İSTATİSTİK BÖLÜMÜ", "normalized_name": "istatistik bolumu",
           "aliases": [{"value": "DEPARTMENT OF STATISTICS", "locale": "en", "source": "yok"}]}
    doc = build_document(sub, build_parent_name_index(parents))
    assert "alias_variants" not in doc
    assert "DEPARTMENT OF STATISTICS" in doc["aliases_text"]


def test_mapping_alias_variants_is_nested() -> None:
    av = build_mapping()["properties"]["alias_variants"]
    assert av["type"] == "nested"
    assert av["properties"]["value"]["analyzer"] == "turkish_analyzer"
    assert set(av["properties"]["value"]["fields"]) == {"ascii"}


# --------------------------------------------------------------------------- #
# hibrit: RRF + kNN kurucu (ES/model gerektirmez)
# --------------------------------------------------------------------------- #
from institution_resolver_v3.elastic.search import build_knn_query, rrf_merge


def test_knn_query_filters_record_type() -> None:
    q = build_knn_query([0.1, 0.2], "subunit", k=50, num_candidates=100)
    assert q["field"] == "embedding"
    assert q["filter"] == {"term": {"record_type": "subunit"}}
    assert q["k"] == 50


def test_rrf_merge_fuses_two_rank_lists() -> None:
    bm25 = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
    knn = [{"id": "B"}, {"id": "A"}, {"id": "D"}]
    out = rrf_merge([bm25, knn], k=60, size=10)
    ids = [h["id"] for h in out]
    # B: 1/62 + 1/61 ; A: 1/61 + 1/62  -> esit; C ve D tek listede
    assert set(ids) == {"A", "B", "C", "D"}
    assert ids[0] in {"A", "B"}                # ikisi de iki listede, en ustte
    assert ids[-1] == "D"                      # id-asc tiebreak: C(2) < D(3) degil...
    # her aday rrf_score tasir
    assert all("rrf_score" in h for h in out)


def test_rrf_prefers_items_in_both_lists() -> None:
    bm25 = [{"id": "X"}, {"id": "only_bm"}]
    knn = [{"id": "X"}, {"id": "only_knn"}]
    out = rrf_merge([bm25, knn], size=10)
    assert out[0]["id"] == "X"                 # iki listede de var -> en yuksek


# --------------------------------------------------------------------------- #
# B2 (2026-08-06): arama yanitinda `_source` beyaz listesi. Bu liste eksik
# kalirsa SESSIZ bozulma olur - alan `None` doner, hata VERMEZ, kalite duser
# (en tehlikelisi country/city: prompt onlari "ZORUNLU kontrol" sayiyor).
# O yuzden liste ve `raw`'dan okunan alan adlari burada sabitlenir.
# --------------------------------------------------------------------------- #
def test_pool_source_fields_covers_every_consumer() -> None:
    """`ScoredCandidate.raw`'dan ad ad okunan TUM alanlar beyaz listede olmali.

    Tuketiciler (2026-08-06 taramasi):
      decompose.py    -> name, aliases
      _attach_signals -> id, record_type, name, aliases
      gate.py         -> parent_id
      resolve.py      -> parent_id
      candidates.py   -> country, city, parent_id, parent_name, kind_label_raw
    Yeni bir tuketici `raw.get("X")` yazarsa bu testi de guncellemeli - aksi
    halde X sessizce None doner.
    """
    from institution_resolver_v3.elastic.search import POOL_SOURCE_FIELDS

    tuketilen = {
        "id", "record_type", "name", "aliases",
        "parent_id", "parent_name", "country", "city", "kind_label_raw",
    }
    assert tuketilen <= set(POOL_SOURCE_FIELDS)


def test_pool_source_excludes_embedding() -> None:
    """`embedding` yanitta ISTENMEZ - belge yukunun %99'u o (16.970/17.388 B).

    Hicbir KARAR yolu kosinus kullanmiyor (gate'te '# gosterim', prompt'tan
    2026-07-27'de cikarildi). kNN retrieval etkilenmez: o ES tarafinda calisir.
    """
    from institution_resolver_v3.elastic.search import POOL_SOURCE_FIELDS

    assert "embedding" not in POOL_SOURCE_FIELDS


def test_search_queries_still_use_unreturned_fields() -> None:
    """Kritik ayrim: `_source` filtresi ARAMAYI etkilemez.

    `alias_variants` (parent) ve `aliases_text` (subunit) yanitta DONMEZ ama
    sorguda ARANMAYA devam eder - ters indeks ile `_source` ayri seylerdir.
    """
    from institution_resolver_v3.elastic.search import POOL_SOURCE_FIELDS

    assert "alias_variants" not in POOL_SOURCE_FIELDS
    assert "aliases_text" not in POOL_SOURCE_FIELDS
    assert "alias_variants" in str(build_search_query("gazi", "parent"))
    assert "aliases_text" in str(build_search_query("istatistik", "subunit"))
