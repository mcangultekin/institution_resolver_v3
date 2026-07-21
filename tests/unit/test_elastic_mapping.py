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


def test_search_query_filters_record_type() -> None:
    q = build_search_query("gazi universitesi", "parent")
    assert q["bool"]["filter"] == [{"term": {"record_type": "parent"}}]
    assert q["bool"]["must"][0]["multi_match"]["fuzziness"] == "AUTO"


def test_subunit_query_includes_parent_name_field() -> None:
    q = build_search_query("istatistik", "subunit")
    fields = q["bool"]["must"][0]["multi_match"]["fields"]
    assert any(f.startswith("parent_name") for f in fields)   # parent enjeksiyonu aramada
    # parent aramasinda parent_name YOK
    qp = build_search_query("gazi", "parent")
    fields_p = qp["bool"]["must"][0]["multi_match"]["fields"]
    assert not any(f.startswith("parent_name") for f in fields_p)


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
