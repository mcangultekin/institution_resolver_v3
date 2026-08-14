"""Prompt varyant mekanizmasi (judge/variants.py + prompt.py `variant` parametresi).

EN KRITIK TEST `test_v1_byte_identical_to_golden`: altin kopya
(`tests/fixtures/prompt_v1_golden.txt`) varyant mekanizmasi EKLENMEDEN ONCE
uretilip donduruldu. Uretim yolunun (variant=None) tek karakteri bile kayarsa
bu test kirmizi doner - "tezgah uretimi degistirmedi" iddiasinin dayanagi budur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from institution_resolver_v3.judge.candidates import CandidateView
from institution_resolver_v3.judge.prompt import build_prompt
from institution_resolver_v3.judge.variants import V1, V3, PromptVariant, get_variant
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "prompt_v1_golden.txt"


def _fixture():
    """Altin kopyayi ureten girdinin BIREBIR aynisi (bicimlendirmenin tum
    dallarini gezer: exact var/yok, alias var/yok, ulke/sehir dolu/bos,
    parent-filtresinden gecmis/gecmemis)."""
    hyps = [
        BoundaryHypothesis("ege universitesi", "tip fakultesi geriatri", 95.5,
                           "EGE ÜNİVERSİTESİ", "152"),
        BoundaryHypothesis("ege", "universitesi tip fakultesi geriatri", 71.0,
                           "EGE A.Ş.", "999"),
    ]
    dq = DecomposedQuery(hyps[0].institution_part, hyps[0].unit_part, hyps[0].boundary_score,
                         hyps[0].matched_parent_name, hyps[0].matched_parent_id, hypotheses=hyps)
    parents = [
        CandidateView(id="P1", name="EGE ÜNİVERSİTESİ", bm25_norm=1.0, cosine=None,
                      token_set_ratio=97.5, qualifier_conflict=False, passed_parent_filter=None,
                      exact_match=True, exact_match_text="ege universitesi",
                      best_alias="EGE UNIVERSITY", country="TR", city="İzmir"),
        CandidateView(id="P2", name="EGE A.Ş.", bm25_norm=0.42, cosine=None,
                      token_set_ratio=33.0, qualifier_conflict=True, passed_parent_filter=None,
                      exact_match=False),
    ]
    subs = [
        CandidateView(id="S1", name="GERİATRİ BİLİM DALI", bm25_norm=0.88, cosine=None,
                      token_set_ratio=64.0, qualifier_conflict=False, passed_parent_filter=True,
                      exact_match=False, best_alias="DIVISION OF GERIATRICS", country="TR",
                      city="İzmir", kind_label="Bilim Dalı", parent_name="EGE ÜNİVERSİTESİ",
                      parent_id="P1"),
        CandidateView(id="S2", name="DAHİLİ TIP BİLİMLERİ BÖLÜMÜ", bm25_norm=0.51, cosine=None,
                      token_set_ratio=58.0, qualifier_conflict=False, passed_parent_filter=False,
                      exact_match=True, exact_match_text="tip fakultesi", parent_id="P9"),
    ]
    return "Ege Üniversitesi Tıp Fakültesi Geriatri Bilim Dalı", dq, parents, subs


def test_v1_byte_identical_to_golden():
    """Uretim yolu (variant verilmemis) altin kopyayla BAYT-DENK olmali."""
    q, dq, p, s = _fixture()
    assert build_prompt(q, dq, p, s) == GOLDEN.read_text(encoding="utf-8")


def test_explicit_v1_equals_default():
    q, dq, p, s = _fixture()
    assert build_prompt(q, dq, p, s, variant=V1) == build_prompt(q, dq, p, s)


class TestV3DeadRules:
    def test_removes_schema_enforced_rules(self):
        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V3)
        assert "listeler arası id kullanmak GEÇERSİZDİR" not in out
        assert "yeni id/ad UYDURMA" not in out
        assert '"parent": {"verdict": "auto_match|review' not in out  # sema ornegi

    def test_keeps_semantic_rules(self):
        """Semanin ZORLAMADIGI icerik kalmali - verdict TANIMLARI, ulke/sehir
        kurali, uc-seviye kurali, unit_phrase yonergesi."""
        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V3)
        assert "doğru görünüyor ama insan onayı önerilir" in out   # review tanimi
        assert "Ülke/şehir tutarlılığı ZORUNLU" in out
        assert "Sorgu ÜÇ seviyeli olabilir" in out
        assert '"unit_phrase"' in out
        assert "TAM_EŞLEŞME NOTU" in out

    def test_is_shorter(self):
        q, dq, p, s = _fixture()
        v1_len = len(build_prompt(q, dq, p, s))
        v3_len = len(build_prompt(q, dq, p, s, variant=V3))
        assert v3_len < v1_len
        # Anlamli bir kisalma olmali - birkac karakterlik fark deney degildir.
        assert v1_len - v3_len > 400

    def test_data_section_untouched(self):
        """Varyant YALNIZ kural bloklarina dokunur; sorgu/hipotez/aday listeleri
        aynen kalmali (yoksa v1<->v3 farki 'model farkli veri gordu' olurdu)."""
        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V3)
        assert q in out
        assert "EGE ÜNİVERSİTESİ" in out and "GERİATRİ BİLİM DALI" in out
        assert 'diğer_adı="EGE UNIVERSITY"' in out


class TestVariantRegistry:
    def test_get_known(self):
        assert get_variant("v1") is V1
        assert get_variant("v3") is V3

    def test_unknown_raises_loudly(self):
        with pytest.raises(KeyError, match="bilinmeyen varyant"):
            get_variant("v99")

    def test_frozen(self):
        with pytest.raises(Exception):
            V1.olu_kurallar = False  # type: ignore[misc]


def test_missing_block_raises_instead_of_silent_noop():
    """Prompt ileride degisir de cikarilacak blok bulunamazsa varyant SESSIZCE
    bos islem yapmamali - yoksa 'olcum yaptik' sanip hicbir sey olcmezdik."""
    from institution_resolver_v3.judge import prompt as prompt_mod

    with pytest.raises(RuntimeError, match="bulunamadi"):
        prompt_mod._apply_variant("alakasiz metin", PromptVariant(name="x", olu_kurallar=False))
