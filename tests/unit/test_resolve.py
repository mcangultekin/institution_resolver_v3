"""retrieve/resolve.py birim testleri - parent-first cascade + sinyaller.

Gercek ES gerektirmez: `search_fn`/`search_knn_fn` (ve decompose icin
`decompose_search_fn`) sahte fonksiyonlarla enjekte edilir. Senaryo: parent
dogru bulunuyor (id=101), subunit'in DOGRU cevabi (id=2) parent_id filtresine
GIRMIYOR (parent tahmini bu senaryoda kismen yanilsa bile) - recall-guvenli
birlesimin onu kaybetmemesi gerekiyor.
"""

from __future__ import annotations

from institution_resolver_v3.normalize.query_pipeline import normalize
from institution_resolver_v3.retrieve.resolve import resolve

_PARENT_POOL = [{"id": "101", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ"}]

_SUB_UNFILTERED = [
    {"id": "1", "record_type": "subunit", "name": "İSTATİSTİK BÖLÜMÜ", "parent_id": "101"},
    {"id": "2", "record_type": "subunit", "name": "İSTATİSTİK ANABİLİM DALI", "parent_id": "999"},
]
_SUB_FILTERED = [_SUB_UNFILTERED[0]]  # sadece parent_id=101 olan


def _score(hits: list[dict], base: float = 50.0) -> list[dict]:
    return [{**h, "score": base - i} for i, h in enumerate(hits)]


def _fake_search_fn(text, record_type, *, extra_filters=None, size=50):
    if record_type == "parent":
        query_tokens = set(normalize(text).base_no_accent.split())
        hits = [h for h in _PARENT_POOL if query_tokens & set(normalize(h["name"]).base_no_accent.split())]
        return _score(hits)
    if extra_filters:
        return _score(_SUB_FILTERED)
    return _score(_SUB_UNFILTERED)


def _fake_search_knn_fn(text, record_type, *, extra_filters=None, size=50):
    # kNN havuzu bos donsun - test sadece BM25/cascade/merge davranisini dogruluyor,
    # cosine=0.0 (kNN havuzunda yok) beklenen default.
    return []


class TestResolveCascade:
    def test_parent_resolved_from_institution_part(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        assert result.decomposed.institution_part == "gazi üniversitesi"
        assert len(result.parents) == 1
        assert result.parents[0].id == "101"

    def test_recall_safe_merge_keeps_subunit_outside_filter(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        ids = [c.id for c in result.subunits]
        assert ids == ["1", "2"]  # filtreli (1) once, filtresizde-kalan (2) sonra

    def test_passed_parent_filter_flag(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        by_id = {c.id: c for c in result.subunits}
        assert by_id["1"].passed_parent_filter is True
        assert by_id["2"].passed_parent_filter is False

    def test_no_parent_found_skips_filter_but_keeps_unfiltered(self):
        result = resolve(
            "bilinmeyen kurum istatistik bölümü",
            search_fn=lambda text, rt, **kw: [] if rt == "parent" else _fake_search_fn(text, rt, **kw),
            search_knn_fn=_fake_search_knn_fn,
        )
        assert result.parents == []
        ids = [c.id for c in result.subunits]
        assert set(ids) == {"1", "2"}
        assert all(c.passed_parent_filter is False for c in result.subunits)


class TestResolveSignals:
    def test_signals_present_and_in_range(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        for cand in result.parents + result.subunits:
            assert 0.0 <= cand.bm25_norm <= 1.0
            assert cand.cosine is None or -1.0 <= cand.cosine <= 1.0
            assert 0.0 <= cand.token_set_ratio <= 100.0
            assert isinstance(cand.qualifier_conflict, bool)

    def test_bm25_norm_is_one_for_top_hit(self):
        # tek adaylik havuzlarda (ör. parent) en yuksek skor kendine bolunur -> 1.0
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        assert result.parents[0].bm25_norm == 1.0

    def test_no_knn_hit_yields_cosine_none(self):
        # kNN havuzu bos donuyor (bkz. _fake_search_knn_fn) - "olculmedi" ile
        # "olculdu, dusuk cikti" (0.0) karistirilmamali (bkz. resolve.py docstring'i).
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
        )
        assert all(c.cosine is None for c in result.parents + result.subunits)
