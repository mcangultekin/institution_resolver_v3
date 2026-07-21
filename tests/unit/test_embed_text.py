"""Embed metni kurucu - model gerektirmeyen yapisal testler."""

from __future__ import annotations

from institution_resolver_v3.embedding.text_builder import build_embed_text


def test_subunit_embed_text_injects_parent_and_all_aliases() -> None:
    rec = {
        "id": "5", "record_type": "subunit", "parent_id": "101",
        "name": "İSTATİSTİK BÖLÜMÜ",
        "aliases": [{"value": "İSTATİSTİK BÖLÜMÜ", "locale": "tr", "source": "legacy_row"},
                    {"value": "DEPARTMENT OF STATISTICS", "locale": "en", "source": "yok"}],
    }
    text = build_embed_text(rec, {"101": "GAZİ ÜNİVERSİTESİ"}, prefix="passage: ")
    assert text.startswith("passage: ")
    assert "İSTATİSTİK BÖLÜMÜ" in text
    assert "GAZİ ÜNİVERSİTESİ" in text                    # PARENT enjeksiyonu
    assert "DEPARTMENT OF STATISTICS" in text             # tum alias'lar
    # ad hem name hem alias'ta vardi -> tek kez (dedup)
    assert text.count("İSTATİSTİK BÖLÜMÜ") == 1


def test_parent_embed_text_has_no_parent_injection() -> None:
    rec = {"id": "101", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ",
           "aliases": [{"value": "GAZI UNIVERSITY", "locale": "en", "source": "ror"}]}
    text = build_embed_text(rec, {}, prefix="passage: ")
    assert "GAZİ ÜNİVERSİTESİ" in text and "GAZI UNIVERSITY" in text


def test_embed_text_natural_case_preserved() -> None:
    # agresif normalize DEGIL - dogal case/aksan korunur (e5 icin)
    rec = {"id": "1", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ", "aliases": []}
    text = build_embed_text(rec, {}, prefix="passage: ")
    assert "GAZİ ÜNİVERSİTESİ" in text                    # kucuk harfe cevrilmedi
