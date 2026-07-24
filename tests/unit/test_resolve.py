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
    # kNN havuzu bos donsun - test sadece BM25/cascade/merge davranisini dogruluyor.
    return []


def _no_cosine_fn(text, hits):
    # Kosinus doldurma kapali (ES/embedding gerektirmesin); None kalir.
    return {}


class TestResolveCascade:
    def test_parent_resolved_from_institution_part(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        assert result.decomposed.institution_part == "gazi üniversitesi"
        assert len(result.parents) == 1
        assert result.parents[0].id == "101"

    def test_recall_safe_merge_keeps_subunit_outside_filter(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        ids = [c.id for c in result.subunits]
        assert ids == ["1", "2"]  # filtreli (1) once, filtresizde-kalan (2) sonra

    def test_passed_parent_filter_flag(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        by_id = {c.id: c for c in result.subunits}
        assert by_id["1"].passed_parent_filter is True
        assert by_id["2"].passed_parent_filter is False

    def test_no_parent_found_skips_filter_but_keeps_unfiltered(self):
        result = resolve(
            "bilinmeyen kurum istatistik bölümü",
            search_fn=lambda text, rt, **kw: [] if rt == "parent" else _fake_search_fn(text, rt, **kw),
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        assert result.parents == []
        ids = [c.id for c in result.subunits]
        assert set(ids) == {"1", "2"}
        assert all(c.passed_parent_filter is False for c in result.subunits)


class TestMultiHypothesisCascade:
    """Coklu-hipotez revizyonu: cascade tek parent degil, hipotezlerin isaret
    ettigi TUM makul parent'larla (terms) filtreler - birincil hipotez yanlissa
    dogru parent'in subunit'i filtreden yine gecer."""

    _PARENTS = [
        {"id": "101", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ"},
        {"id": "1", "record_type": "parent", "name": "ANKARA ÜNİVERSİTESİ"},
    ]
    _SUBS = [
        {"id": "11", "record_type": "subunit", "name": "İSTATİSTİK BÖLÜMÜ", "parent_id": "101"},
        {"id": "12", "record_type": "subunit", "name": "İSTATİSTİK ANABİLİM DALI", "parent_id": "1"},
    ]

    def _run(self):
        captured: dict = {}

        def fake(text, rt, *, extra_filters=None, size=50):
            if rt == "parent":
                qt = set(normalize(text).base_no_accent.split())
                return _score(
                    [h for h in self._PARENTS if qt & set(normalize(h["name"]).base_no_accent.split())]
                )
            if extra_filters:
                captured["filters"] = extra_filters
                allowed = set(extra_filters[0]["terms"]["parent_id"])
                return _score([h for h in self._SUBS if h["parent_id"] in allowed])
            return _score(self._SUBS)

        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=fake,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        return result, captured

    def test_terms_filter_covers_alternate_hypothesis_parents(self):
        result, captured = self._run()
        cascade_ids = captured["filters"][0]["terms"]["parent_id"]
        assert cascade_ids[0] == "101"  # en guclu parent adayi basta
        assert "1" in cascade_ids  # alternatif hipotezin parent'i da filtrede

    def test_alternate_parent_subunit_passes_filter(self):
        result, _ = self._run()
        by_id = {c.id: c for c in result.subunits}
        assert by_id["11"].passed_parent_filter is True
        assert by_id["12"].passed_parent_filter is True

    def test_parent_union_keeps_primary_first(self):
        result, _ = self._run()
        assert result.parents[0].id == "101"
        assert {c.id for c in result.parents} == {"101", "1"}

    def test_hypothesis_parent_injected_when_missing_from_pool(self):
        # Hipotezin parent'i havuz aramasinin top-K'sina girmese bile hakem icin
        # aday listesinde bulunmali (asgari sinyallerle enjekte edilir).
        dsf = lambda text, rt: [{"id": "77", "name": "GAZİ ÜNİVERSİTESİ"}]  # noqa: E731
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=lambda text, rt, **kw: [] if rt == "parent" else _fake_search_fn(text, rt, **kw),
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
            decompose_search_fn=dsf,
        )
        assert [c.id for c in result.parents] == ["77"]
        injected = result.parents[0]
        assert injected.raw.get("from_hypothesis_only") is True
        assert injected.bm25_norm == 0.0
        assert injected.cosine is None


class TestResolveSignals:
    def test_signals_present_and_in_range(self):
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
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
            cosine_fn=_no_cosine_fn,
        )
        assert result.parents[0].bm25_norm == 1.0

    def test_cosine_none_only_when_fill_cannot_compute(self):
        # cosine_fn hicbir sey hesaplayamazsa None KALIR ("vektor yok/alinamadi") -
        # 0.0'a cevrilmez (bkz. resolve.py docstring'i).
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        assert all(c.cosine is None for c in result.parents + result.subunits)

    def test_cosine_filled_for_non_knn_candidates(self):
        # kNN havuzu bos olsa bile cosine_fn her aday icin kosinusu doldurur -
        # hakem tam vektor kaniti gorur (2026-07-24 revizyonu).
        def fake_cosine(text, hits):
            return {h["id"]: 0.9 for h in hits}

        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=fake_cosine,
        )
        assert result.parents and result.subunits
        for cand in result.parents + result.subunits:
            assert cand.cosine is not None
            assert abs(cand.cosine - 0.9) < 1e-9  # (c+1)/2 -> 2s-1 gidis-donusu kayipsiz
