"""normalize/query_pipeline.py birim testleri.

EXPERIMENTS.md'de belgelenen davranis kurallarini assert'e cevirir:
Turkce I/i cevrimi, locale-bagimsiz icerik-tabanli kucuk-harfleme,
aksan temizligi, gorunmez karakter/whitespace normalizasyonu ve
`normalize()`'in adim sirasina bagli davranisi (kisaltma genisletmesi
kucuk-harflemeden ONCE calismali - noktalama silinmeden once).
"""

from __future__ import annotations

from institution_resolver_v3.normalize.query_pipeline import (
    clean_punctuation,
    expand_query_text,
    locale_aware_lower,
    normalize,
    normalize_whitespace,
    strip_turkish_accents,
    turkish_lower,
)


class TestTurkishLower:
    def test_dotted_capital_i_to_dotted_lower_i(self):
        assert turkish_lower("İSTANBUL") == "istanbul"

    def test_dotless_capital_i_to_dotless_lower_i(self):
        # ASCII "I" Turkce kuralinda noktasiz "i" olmali, Python str.lower() "i" YAPAR (yanlis)
        assert turkish_lower("TIP") == "tıp"
        assert turkish_lower("TIP") != "tip"

    def test_other_turkish_letters(self):
        assert turkish_lower("ŞĞÜÖÇ") == "şğüöç"


class TestLocaleAwareLower:
    def test_uses_turkish_rules_when_turkish_specific_char_present(self):
        # icerik kaniti: metinde "İ" var -> turkish_lower uygulanmali (TIP -> tıp)
        result = locale_aware_lower("TIP FAKÜLTESİ")
        assert result == "tıp fakültesi"

    def test_falls_back_to_plain_lower_for_pure_ascii(self):
        # Turkce'ye ozgu karakter yoksa ayirt edilemez -> duz .lower()
        assert locale_aware_lower("TECHNICAL UNIVERSITY") == "technical university"

    def test_locale_label_does_not_override_content_evidence(self):
        # locale="en" etiketlenmis olsa bile Turkce karakter iceriyorsa Turkce kurali uygulanir
        assert locale_aware_lower("TIP FAKÜLTESİ", locale="en") == "tıp fakültesi"


class TestStripTurkishAccents:
    def test_strips_accented_chars(self):
        assert strip_turkish_accents("çğıöşü") == "cgiosu"

    def test_leaves_ascii_untouched(self):
        assert strip_turkish_accents("university") == "university"


class TestNormalizeWhitespace:
    def test_collapses_multiple_spaces(self):
        assert normalize_whitespace("gazi   üniversitesi") == "gazi üniversitesi"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_whitespace("  gazi üniversitesi  ") == "gazi üniversitesi"

    def test_replaces_nbsp(self):
        assert normalize_whitespace("gazi üniversitesi") == "gazi üniversitesi"

    def test_replaces_zwsp(self):
        assert normalize_whitespace("gazi​üniversitesi") == "gazi üniversitesi"

    def test_replaces_bom(self):
        assert normalize_whitespace("﻿gazi üniversitesi") == "gazi üniversitesi"


class TestCleanPunctuation:
    def test_replaces_punctuation_with_space(self):
        assert clean_punctuation("fen-edebiyat fakültesi") == "fen edebiyat fakültesi"

    def test_preserves_alphanumerics(self):
        assert clean_punctuation("2. öğretim") == "2  öğretim"


class TestExpandQueryText:
    def test_preserves_case_and_accents(self):
        # yalnizca kisaltma genisletmesi + gorunmez-karakter temizligi yapar,
        # goruntu yapisini (buyuk/kucuk harf, aksan) BOZMAZ
        result = expand_query_text("Gazi Üni Fen Fak.")
        assert "Gazi" in result
        assert "ÜNİVERSİTE" in result

    def test_does_not_lowercase(self):
        result = expand_query_text("ANKARA")
        assert result == "ANKARA"

    def test_expands_known_abbreviation(self):
        result = expand_query_text("gazi üni")
        assert "ÜNİVERSİTESİ" in result


class TestNormalizeStepOrder:
    def test_abbreviation_expands_before_punctuation_strips_dots(self):
        # kisaltma genisletmesi noktaya dayanir; noktalama temizliginden ONCE calismali
        result = normalize("gazi üni. fen fak.")
        assert "üniversite" in result.base
        assert "fakülte" in result.base

    def test_base_has_no_accents_stripped(self):
        result = normalize("gazi üniversitesi")
        assert "ü" in result.base

    def test_base_no_accent_has_accents_stripped(self):
        result = normalize("gazi üniversitesi")
        assert "ü" not in result.base_no_accent
        assert "u" in result.base_no_accent

    def test_turkish_i_conversion_applied_in_full_pipeline(self):
        result = normalize("TIP FAKÜLTESİ")
        assert result.base.startswith("tıp")

    def test_raw_field_untouched(self):
        raw = "  Gazi  Üni.  "
        result = normalize(raw)
        assert result.raw == raw

    def test_tokens_property(self):
        result = normalize("gazi üniversitesi fen fakültesi")
        assert result.tokens == ["gazi", "üniversitesi", "fen", "fakültesi"]

    def test_empty_string_yields_empty_tokens(self):
        result = normalize("")
        assert result.tokens == []

    def test_abbreviation_expansion_can_be_disabled(self):
        result = normalize("gazi üni.", expand_abbreviations=False)
        assert "üniversite" not in result.base
