"""Havuz kalitesi kapisi - ayirt edici token kapsamasi (retrieve/token_df.py)."""

from __future__ import annotations

import pytest

from institution_resolver_v3.retrieve.token_df import (
    GATE_MODES,
    build_token_df,
    gate_pool,
    orphan_tokens,
)


class _Aday:
    def __init__(self, name, aliases=(), passed=None):
        self.name = name
        self.raw = {"aliases": list(aliases)}
        self.passed_parent_filter = passed


def test_df_counts_records_not_occurrences():
    """Dokuman frekansi: adinda iki kez gecen token o kaydi BIR kez sayar."""
    df = build_token_df([
        {"name": "Ordu Ordu Üniversitesi", "aliases": []},
        {"name": "Bursa Üniversitesi", "aliases": [{"value": "Bursa University"}]},
    ])
    assert df["ordu"] == 1
    assert df["universitesi"] == 2
    assert df["university"] == 1


class TestOrphanTokens:
    """Olculen uc vaka (2026-08-14) - hepsinde tsr YUKSEKTI, kapi onu yakalar."""

    def test_identity_token_missing_from_pool(self):
        df = {"buyuksehir": 3, "belediyesi": 6, "malatya": 3, "ordu": 2}
        havuz = [_Aday("Ordu Büyükşehir Belediyesi")]
        assert orphan_tokens("Malatya Büyükşehir Belediyesi", havuz, df) == ["malatya"]

    def test_silent_when_identity_covered(self):
        df = {"buyuksehir": 3, "belediyesi": 6, "malatya": 3}
        havuz = [_Aday("Malatya Büyükşehir Belediyesi")]
        assert orphan_tokens("Malatya Büyükşehir Belediyesi", havuz, df) == []

    def test_alias_counts_as_coverage(self):
        df = {"afad": 2}
        havuz = [_Aday("Afet ve Acil Durum Yönetimi Başkanlığı", ["AFAD"])]
        assert orphan_tokens("AFAD", havuz, df) == []

    def test_generic_token_never_orphan(self):
        """Yaygin token (df > esik) kimlik tasimaz - havuzda olmasa da oksuz sayilmaz."""
        df = {"university": 11607, "sydney": 3}
        assert orphan_tokens("University", [_Aday("Başka Kurum")], df) == []

    def test_typo_is_not_orphan(self):
        """'Ünitversitesi' (df=0) havuzdaki 'üniversitesi'ye fuzzy yakin - yazim
        hatasi olan her dogru sorgu haksiz yere bloklanmamali."""
        df = {"unitversitesi": 0, "ordu": 2, "universitesi": 322}
        havuz = [_Aday("ORDU ÜNİVERSİTESİ")]
        assert orphan_tokens("Ordu Ünitversitesi", havuz, df) == []

    def test_diacritic_variant_is_not_orphan(self):
        """'brasov' vs 'brașov' = 83 benzerlik; 85 esikte haksiz bloklaniyordu."""
        df = {"brasov": 1, "transilvania": 0}
        havuz = [_Aday("Transylvania University of Brașov", ["Universitatea Transilvania"])]
        assert "brasov" not in orphan_tokens("Transilvania University of Brasov", havuz, df)

    def test_short_tokens_ignored(self):
        """'T.C.' -> 't','c' parcalari kimlik tasimaz."""
        df = {"t": 0, "c": 0, "ticaret": 4}
        assert orphan_tokens("T.C. Ticaret", [_Aday("Ticaret Bakanlığı")], df) == []


class TestGatePool:
    def test_parent_mode(self):
        class R:
            parents = [_Aday("A")]
            subunits = [_Aday("S", passed=True)]
        assert [c.name for c in gate_pool(R(), "parent")] == ["A"]

    def test_parent_filtered_mode_includes_only_filtered_subunits(self):
        class R:
            parents = [_Aday("A")]
            subunits = [_Aday("S1", passed=True), _Aday("S2", passed=False)]
        assert [c.name for c in gate_pool(R(), "parent_filtered")] == ["A", "S1"]

    def test_unknown_mode_raises(self):
        class R:
            parents = []
            subunits = []
        with pytest.raises(ValueError, match="bilinmeyen kapi modu"):
            gate_pool(R(), "hepsi")

    def test_modes_declared(self):
        assert GATE_MODES == ("parent", "parent_filtered")
