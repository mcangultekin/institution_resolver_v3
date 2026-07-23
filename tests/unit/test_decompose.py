"""retrieve/decompose.py birim testleri.

Gercek ES gerektirmez: `search_fn` sahte bir BM25 taklidi (paylasilan normalize
edilmis token varsa aday havuzundan dondurur) ile enjekte edilir - boylece
decompose'un SECIM mantigi (fuzz.ratio ile sinir tespiti), ES'in kendi arama
kalitesinden bagimsiz test edilir. Havuzdaki adlar docs/DURUM.md'de
belgelenen gercek veri dogrulamasindan alinmistir (bkz. decompose.py docstring'i).
"""

from __future__ import annotations

from institution_resolver_v3.normalize.query_pipeline import normalize
from institution_resolver_v3.retrieve.decompose import decompose

_POOL = [
    {
        "id": "900",
        "name": "Japan Agency for Marine-Earth Science and Technology",
        "aliases": ["JAMSTEC", "Japan Agency for Marine-Earth Science and Technology"],
    },
    {"id": "101", "name": "GAZİ ÜNİVERSİTESİ"},
    {"id": "1", "name": "ANKARA ÜNİVERSİTESİ"},
    {"id": "2", "name": "ESKİŞEHİR OSMANGAZİ ÜNİVERSİTESİ"},
    {"id": "3", "name": "Eskişehir Osmangazi Üniversitesi Tıp Fakültesi Hastanesi"},
    {"id": "4", "name": "University of Oxford"},
    {"id": "5", "name": "Gazi Hastanesi"},
    {"id": "6", "name": "Razi University"},
]


def _fake_search(text: str, record_type: str) -> list[dict]:
    assert record_type == "parent"
    query_tokens = set(normalize(text).base_no_accent.split())
    hits = []
    for rec in _POOL:
        indexed = " ".join([rec["name"], *rec.get("aliases", [])])
        name_tokens = set(normalize(indexed).base_no_accent.split())
        if query_tokens & name_tokens:
            hits.append(rec)
    return hits


class TestDecompose:
    def test_splits_at_institution_boundary(self):
        result = decompose("gazi üniversitesi istatistik bölümü", search_fn=_fake_search)
        assert result.institution_part == "gazi üniversitesi"
        assert result.unit_part == "istatistik bölümü"
        assert result.matched_parent_id == "101"
        assert result.boundary_score > 95

    def test_english_of_pattern_not_split_at_bare_marker(self):
        # "University of Oxford" - isaretci ("university") kurumun adini
        # BASLATIYOR; ilk-kelime kuralinda kirilirdi, burada dogru bolunmeli.
        result = decompose("university of oxford department of physics", search_fn=_fake_search)
        assert result.institution_part == "university of oxford"
        assert result.unit_part == "department of physics"
        assert result.matched_parent_id == "4"

    def test_compound_institution_name_not_truncated(self):
        # Bilesik ad: zincirleme marker'lar TEK bir kurumun kendi adi.
        query = "eskişehir osmangazi üniversitesi tıp fakültesi hastanesi"
        result = decompose(query, search_fn=_fake_search)
        assert result.institution_part == query
        assert result.unit_part == ""
        assert result.matched_parent_id == "3"

    def test_unit_before_institution(self):
        # Kullanici raporu: birim once yazilirsa onek-taramasi hic bolemiyordu
        # (tum sorgu tek parca kaliyordu). Alt-dizge taramasi bunu cozer.
        result = decompose("istatistik bölümü gazi üniversitesi", search_fn=_fake_search)
        assert result.institution_part == "gazi üniversitesi"
        assert result.unit_part == "istatistik bölümü"
        assert result.matched_parent_id == "101"
        assert result.boundary_score > 95

    def test_unit_before_institution_single_word(self):
        result = decompose("fen fakültesi gazi üniversitesi", search_fn=_fake_search)
        assert result.institution_part == "gazi üniversitesi"
        assert result.unit_part == "fen fakültesi"
        assert result.matched_parent_id == "101"

    def test_no_institution_in_query_yields_low_confidence(self):
        result = decompose("istatistik bölümü", search_fn=_fake_search)
        assert result.boundary_score < 90

    def test_whole_query_is_institution_name(self):
        result = decompose("ankara üniversitesi", search_fn=_fake_search)
        assert result.institution_part == "ankara üniversitesi"
        assert result.unit_part == ""

    def test_empty_query(self):
        result = decompose("", search_fn=_fake_search)
        assert result.institution_part == ""
        assert result.unit_part == ""
        assert result.boundary_score == 0.0
        assert result.hypotheses == []


class TestHypotheses:
    def test_primary_mirrors_first_hypothesis(self):
        result = decompose("gazi üniversitesi istatistik bölümü", search_fn=_fake_search)
        assert result.hypotheses
        h0 = result.hypotheses[0]
        assert (result.institution_part, result.unit_part) == (h0.institution_part, h0.unit_part)
        assert result.matched_parent_id == h0.matched_parent_id
        assert result.boundary_score == h0.boundary_score

    def test_hypotheses_point_to_distinct_parents(self):
        result = decompose("gazi üniversitesi istatistik bölümü", search_fn=_fake_search)
        ids = [h.matched_parent_id for h in result.hypotheses]
        assert len(ids) == len(set(ids))

    def test_alternate_parents_included(self):
        # "üniversitesi" penceresi baska universitelere de (Ankara/Osmangazi)
        # ortusuyor - dogru cevap birincil (101) olsa da farkli parent'lara
        # isaret eden alternatif hipotezler listede kalmali (secim decompose'un
        # isi degil, asagi katmanlarin).
        result = decompose("gazi üniversitesi istatistik bölümü", search_fn=_fake_search)
        assert result.hypotheses[0].matched_parent_id == "101"
        alternate_ids = {h.matched_parent_id for h in result.hypotheses[1:]}
        assert alternate_ids  # en az bir alternatif var
        assert "101" not in alternate_ids

    def test_acronym_alias_creates_hypothesis(self):
        # Kanitli kacak sinifi: sorgu akronim/Ingilizce alias'la gelir, kayit
        # farkli kanonik adla durur. Skor name'e EK alias'lara karsi da
        # hesaplanmali - yoksa hipotez hic dogmuyor (30-sorgu duman testi).
        result = decompose("jamstec ocean drilling department", search_fn=_fake_search)
        assert result.hypotheses[0].matched_parent_id == "900"
        assert result.hypotheses[0].institution_part == "jamstec"
        assert result.hypotheses[0].boundary_score == 100.0

    def test_hypotheses_sorted_by_score(self):
        result = decompose("gazi üniversitesi istatistik bölümü", search_fn=_fake_search)
        scores = [h.boundary_score for h in result.hypotheses]
        assert scores == sorted(scores, reverse=True)
