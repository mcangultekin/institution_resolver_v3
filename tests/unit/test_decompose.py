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
        name_tokens = set(normalize(rec["name"]).base_no_accent.split())
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
