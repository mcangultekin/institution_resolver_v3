"""normalize/qualifiers.py birim testleri.

EXPERIMENTS.md'de belgelenen dogrulama sorgularini assert'e cevirir.

NOT (K2, ACTION_PLAN.md 1B): `TestDegreeYL.test_yl_in_parentheses_is_detected`
bu dosya yazildigi anda BILEREK KIRMIZI - `\\b\\(yl\\)\\b` regex'i asla
eslesmiyor (parantez '(' bir kelime-sinir karakteri degil, oncesinde
bosluk oldugunda \\b olusmaz). K2 duzeltmesi (`\\(\\s*yl\\s*\\)`)
uygulandiginda bu test yesile donmeli - bkz. REVIEW_RAPORU.md #K2.
"""

from __future__ import annotations

from institution_resolver_v3.normalize.qualifiers import (
    extract_qualifiers,
    qualifier_match_score,
    qualifiers_conflict,
)


class TestDegreeDR:
    def test_parenthesized_dr_is_doctorate(self):
        assert extract_qualifiers("EBELİK (DR)")["degree"] == "phd"

    def test_bare_dr_title_does_not_produce_false_degree(self):
        # "Prof. Dr. Cemil Tasciouglu" gibi kurum isimlerinde CIPLAK "dr" bir
        # unvandir, doktora niteligi degil - bile bile sadece "(dr)" destekleniyor.
        result = extract_qualifiers("Prof. Dr. Cemil Taşçıoğlu Devlet Hastanesi")
        assert result["degree"] is None

    def test_full_word_doktora_is_detected(self):
        assert extract_qualifiers("işletme doktora programı")["degree"] == "phd"


class TestDegreeYL:
    def test_yl_in_parentheses_is_detected(self):
        # K2 bug'i: EXPERIMENTS.md'ye gore YL en yaygin qualifier (40.802 kayit)
        # ama '(YL)' hicbir zaman eslesmiyordu (\b '(' onunde olusmuyor).
        result = extract_qualifiers("EBELİK (YL) (TEZLİ)")
        assert result["degree"] == "yl"

    def test_full_word_yuksek_lisans_is_detected(self):
        assert extract_qualifiers("işletme yüksek lisans")["degree"] == "yl"

    def test_master_keyword_is_detected(self):
        assert extract_qualifiers("business master program")["degree"] == "yl"


class TestModalityIO:
    def test_parenthesized_io_is_second_education(self):
        result = extract_qualifiers("EBELİK (YL) (TEZLİ) (İÖ)")
        assert result["modality"] == "ikinci_ogretim"

    def test_full_phrase_ikinci_ogretim(self):
        result = extract_qualifiers("ikinci öğretim programı")
        assert result["modality"] == "ikinci_ogretim"

    def test_uzaktan_egitim_with_correct_accents(self):
        result = extract_qualifiers("uzaktan öğretim")
        assert result["modality"] == "uzaktan"


class TestThesisAsciiFold:
    def test_with_thesis_ascii_uppercase_matches(self):
        # "WITH THESIS" -> turkish_lower Ingilizce ASCII I'yi yanlislikla "ı"ya
        # cevirir ("wıth thesıs"); aksan-katlama (strip_turkish_accents) bunu
        # geri "i"ye indirger, boylece "\bwith thesis\b" yine eslesir.
        result = extract_qualifiers("MBA WITH THESIS")
        assert result["thesis"] is True

    def test_tezsiz_lowercase(self):
        assert extract_qualifiers("işletme tezsiz yüksek lisans")["thesis"] is False

    def test_tezli(self):
        assert extract_qualifiers("işletme tezli yüksek lisans")["thesis"] is True


class TestLanguagePatterns:
    def test_english(self):
        assert extract_qualifiers("business administration (english)")["language"] == "en"

    def test_turkish(self):
        assert extract_qualifiers("işletme (türkçe)")["language"] == "tr"

    def test_german(self):
        assert extract_qualifiers("makine mühendisliği (almanca)")["language"] == "de"

    def test_french_ascii_and_accented_both_match(self):
        assert extract_qualifiers("fransızca öğretmenliği")["language"] == "fr"
        assert extract_qualifiers("fransizca ogretmenligi")["language"] == "fr"

    def test_arabic(self):
        assert extract_qualifiers("arapça öğretmenliği")["language"] == "ar"

    def test_russian(self):
        assert extract_qualifiers("rusça mütercim tercümanlık")["language"] == "ru"

    def test_spanish(self):
        assert extract_qualifiers("ispanyolca öğretmenliği")["language"] == "es"


class TestExtraTags:
    def test_interdisciplinary(self):
        assert "interdisciplinary" in extract_qualifiers("(disiplinlerarası)")["extra"]

    def test_full_scholarship(self):
        assert "full_scholarship" in extract_qualifiers("(tam burslu)")["extra"]

    def test_paid(self):
        assert "paid" in extract_qualifiers("(ücretli)")["extra"]

    def test_no_extra_when_absent(self):
        assert extract_qualifiers("fen fakültesi")["extra"] == []


class TestNoQualifierIsAllNone:
    def test_plain_name_has_no_qualifiers(self):
        result = extract_qualifiers("gazi üniversitesi fen fakültesi")
        assert result == {"thesis": None, "modality": None, "language": None, "degree": None, "extra": []}


class TestQualifiersConflict:
    def test_conflicting_thesis_values_conflict(self):
        query = extract_qualifiers("tezli yüksek lisans")
        candidate = extract_qualifiers("tezsiz yüksek lisans")
        assert qualifiers_conflict(query, candidate) is True

    def test_matching_values_do_not_conflict(self):
        query = extract_qualifiers("tezli yüksek lisans")
        candidate = extract_qualifiers("tezli yüksek lisans (i̇ö)")
        assert qualifiers_conflict(query, candidate) is False

    def test_unspecified_side_never_conflicts(self):
        query = extract_qualifiers("işletme")  # nitelik belirtilmemis
        candidate = extract_qualifiers("işletme tezli yüksek lisans")
        assert qualifiers_conflict(query, candidate) is False

    def test_extra_does_not_participate_in_conflict(self):
        query = extract_qualifiers("işletme (tam burslu)")
        candidate = extract_qualifiers("işletme (ücretli)")
        assert qualifiers_conflict(query, candidate) is False


class TestQualifierMatchScore:
    def test_neutral_score_when_query_specifies_nothing(self):
        query = extract_qualifiers("gazi üniversitesi")
        candidate = extract_qualifiers("gazi üniversitesi tezli yüksek lisans")
        assert qualifier_match_score(query, candidate) == 0.5

    def test_full_match_when_all_specified_dimensions_agree(self):
        query = extract_qualifiers("tezli yüksek lisans")
        candidate = extract_qualifiers("tezli yüksek lisans")
        assert qualifier_match_score(query, candidate) == 1.0

    def test_partial_match_scores_between_zero_and_one(self):
        query = extract_qualifiers("tezli yüksek lisans (i̇ngilizce)")
        candidate = extract_qualifiers("tezsiz yüksek lisans (i̇ngilizce)")
        # thesis uyusmuyor, degree+language uyusuyor -> 2/3
        score = qualifier_match_score(query, candidate)
        assert 0 < score < 1
