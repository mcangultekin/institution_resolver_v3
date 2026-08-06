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

    def test_exact_match_true_when_name_is_contiguous_part_of_query(self):
        # 2026-07-24 revizyonu (kullanici bulgusu): birlesik "kurum+birim"
        # sorgularinda kurum adi sorgunun SADECE bir parcasidir - ilk surum
        # TAM sorgu==ad esitligi istiyordu, bu yuzden bu (en yaygin!) durumda
        # HICBIR ZAMAN True olmuyordu. Simdi: ad, sorgunun ARDIŞIK bir
        # parcasiysa (kelime siniri gozetilerek) True.
        result = resolve(
            "gazi üniversitesi istatistik bölümü",
            search_fn=_fake_search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        assert result.parents[0].exact_match is True

    def test_exact_match_false_when_name_tokens_not_contiguous(self):
        # token_set_ratio SIRA/BITISIKLIK gozetmez (token kumesi orten her
        # sey yuksek skor alir) - exact_match bunu KARISTIRMAZ, adin
        # kelimeleri sorguda ARDIŞIK gecmiyorsa (araya baska kelime girmisse)
        # False kalir.
        def search_fn(text, record_type, *, extra_filters=None, size=50):
            if record_type != "parent":
                return []
            qt = set(normalize(text).base_no_accent.split())
            hits = [h for h in _PARENT_POOL if qt & set(normalize(h["name"]).base_no_accent.split())]
            return _score(hits)

        result = resolve(
            "gazi istatistik üniversitesi",  # "istatistik" GAZI ile ÜNİVERSİTESİ arasina girmis
            search_fn=search_fn,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        assert result.parents[0].token_set_ratio >= 90.0  # token kumesi hala ortusuyor
        assert result.parents[0].exact_match is False


class TestExactMatchSignal:
    """2026-07-24, kullanici talebi: sorgu (normalize) adayin adi/alias'larindan
    BIRIYLE BIREBIR ayniysa exact_match=True - "P" bayragiyla ayni mantik,
    ayri/guclu bir kanit (bkz. resolve.py, judge/prompt.py "TAM_EŞLEŞME NOTU")."""

    _POOL = [
        {"id": "1", "record_type": "parent", "name": "Gazi Üniversitesi", "aliases": []},
        {"id": "2", "record_type": "parent", "name": "GÜ", "aliases": ["Gazi Universitesi"]},
    ]

    def _search(self, text, record_type, *, extra_filters=None, size=50):
        if record_type != "parent":
            return []
        qt = set(normalize(text).base_no_accent.split())
        hits = [h for h in self._POOL if qt & set(normalize(h["name"]).base_no_accent.split())]
        return _score(hits)

    def test_exact_name_match(self):
        result = resolve(
            "gazi üniversitesi",
            search_fn=self._search,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        by_id = {c.id: c for c in result.parents}
        assert by_id["1"].exact_match is True

    def test_exact_alias_match(self):
        # "GÜ" adi tek basina query ile eslesmiyor (search_fn tokenle buluyor
        # olsa da) - burada dogrudan aday havuzuna girdigini varsayiyoruz,
        # asil test: alias listesindeki deger sorguyla BIREBIR uysun.
        def search_with_gu(text, record_type, *, extra_filters=None, size=50):
            if record_type != "parent":
                return []
            return _score(self._POOL)  # ikisini de dondur (search kalitesini test etmiyoruz)

        result = resolve(
            "gazi universitesi",  # aksansiz - alias "Gazi Universitesi" ile TAM ayni normalize
            search_fn=search_with_gu,
            search_knn_fn=_fake_search_knn_fn,
            cosine_fn=_no_cosine_fn,
        )
        by_id = {c.id: c for c in result.parents}
        assert by_id["2"].exact_match is True
        assert by_id["1"].exact_match is True  # "Gazi Üniversitesi" de ayni normalize'a denk gelir


# --------------------------------------------------------------------------- #
# B4 (2026-08-06): kNN'e girmemis adaylar icin kosinusu AYRICA hesaplama adimi
# varsayilan olarak KAPALI. Kosinus hicbir karar yoluna girmiyor (gate
# tsr/exact/span kullanir, prompt'tan 814437b ile cikarildi) ve havuz sirasini
# etkilemiyor (RRF ham listelerle calisir).
# --------------------------------------------------------------------------- #
class TestB4CosineFlag:
    def test_default_does_not_compute_cosine_for_non_knn(self):
        """Varsayilan: cosine_fn CAGRILMAZ - pahali yol (encode+mget+numpy) atlanir."""
        cagrildi = []

        def izleyen_cosine(text, hits):
            cagrildi.append(len(hits))
            return {}

        from institution_resolver_v3.retrieve import resolve as R

        orij = R._default_cosine_fn
        R._default_cosine_fn = izleyen_cosine
        try:
            R.resolve(
                "gazi universitesi",
                search_fn=_fake_search_fn,
                search_knn_fn=_fake_search_knn_fn,
                decompose_search_fn=lambda t, rt: _fake_search_fn(t, rt),
            )
        finally:
            R._default_cosine_fn = orij
        assert cagrildi == []            # hic cagrilmadi

    def test_with_cosine_true_restores_old_behaviour(self):
        """with_cosine=True eski davranisi geri getirir (gosterim/hata ayiklama)."""
        cagrildi = []

        def izleyen_cosine(text, hits):
            cagrildi.append(len(hits))
            return {}

        from institution_resolver_v3.retrieve import resolve as R

        orij = R._default_cosine_fn
        R._default_cosine_fn = izleyen_cosine
        try:
            R.resolve(
                "gazi universitesi",
                with_cosine=True,
                search_fn=_fake_search_fn,
                search_knn_fn=_fake_search_knn_fn,
                decompose_search_fn=lambda t, rt: _fake_search_fn(t, rt),
            )
        finally:
            R._default_cosine_fn = orij
        assert cagrildi                  # cagrildi

    def test_knn_candidates_still_get_cosine_for_free(self):
        """kNN top-K'ya GIREN adaylar kosinusunu ES skorundan almaya devam eder.

        B4 yalnizca "listede yoktu, AYRICA hesaplayalim" adimini kaldirir; kNN
        yanitiyla zaten gelen skor (cosine -> (c+1)/2) geri cevrilmeye devam
        eder (2s-1). Bu ayrim korunmazsa vektor kaniti tamamen kaybolurdu.
        """
        from institution_resolver_v3.retrieve import resolve as R

        # kNN havuzu parent 101'i dondursun; ES skoru (kosinus+1)/2 uzayinda
        def knn_fn(text, record_type, *, extra_filters=None, size=50):
            if record_type == "parent":
                return [{**_PARENT_POOL[0], "score": 0.95}]  # -> kosinus 0.90
            return []

        r = R.resolve(
            "gazi universitesi",
            search_fn=_fake_search_fn,
            search_knn_fn=knn_fn,
            decompose_search_fn=lambda t, rt: _fake_search_fn(t, rt),
        )
        aday = [c for c in r.parents if c.id == "101"]
        assert aday, "test verisi anlamsiz: 101 havuzda olmali"
        assert aday[0].cosine is not None
        assert abs(aday[0].cosine - 0.90) < 1e-9            # 2*0.95-1, kayipsiz
