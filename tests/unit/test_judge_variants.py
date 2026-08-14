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
from institution_resolver_v3.judge.variants import V1, V3, V4, PromptVariant, get_variant
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN = _FIX / "prompt_v1_golden.txt"
GOLDEN_V3 = _FIX / "prompt_v3_golden.txt"


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


def test_v3_byte_identical_to_golden():
    """v3'un ciktisi 14 Agustos'ta 125 sorguda OLCULDU (35 fark tek tek
    incelendi). Bayraklar iki parcaya ayrilirken metin kaymamali - kaysaydi
    o olcum bugunku kodla karsilastirilamaz hale gelirdi."""
    q, dq, p, s = _fixture()
    assert build_prompt(q, dq, p, s, variant=V3) == GOLDEN_V3.read_text(encoding="utf-8")


def test_flags_are_independent():
    """Iki bayrak birbirinden bagimsiz: v4 = yalniz kurallari, ters varyant =
    yalniz sema ornegini cikarir; ikisi birlikte v3'u verir."""
    q, dq, p, s = _fixture()
    yalniz_ornek_yok = PromptVariant(name="x", sema_zorunlu_kurallar=True, sema_ornegi=False)
    a = build_prompt(q, dq, p, s, variant=V1)
    b = build_prompt(q, dq, p, s, variant=V4)              # kurallar cikti
    c = build_prompt(q, dq, p, s, variant=yalniz_ornek_yok)  # ornek cikti
    d = build_prompt(q, dq, p, s, variant=V3)              # ikisi de cikti
    assert len(a) > len(b) > len(d) and len(a) > len(c) > len(d)
    assert (len(a) - len(b)) + (len(a) - len(c)) == len(a) - len(d)  # toplanabilir


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


class TestV4:
    """v4 = sema-zorunlu kural bloklari CIKAR, sema ornegi KALIR.

    14 Agustos olcumunden dogdu: v3'un iki etkisi zit yonde ve FARKLI
    bloklardan geliyordu (16 kazanc kurallardan, 18 kayip sema ornegini
    kaybetmekten). v4 kazandiran tarafi alip hasar vereni birakiyor.
    """

    def test_removes_schema_enforced_rules_like_v3(self):
        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V4)
        assert "listeler arası id kullanmak GEÇERSİZDİR" not in out
        assert "yeni id/ad UYDURMA" not in out

    def test_keeps_schema_example_unlike_v3(self):
        """ASIL FARK: `| null` isaretleri modelin null secenegini goren tek
        ipucu - gramer izin veriyor ama zorlamiyor (v3'te kaybedilince 11
        ciplak kurum sorgusunda subunit null yerine no_match oldu)."""
        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V4)
        assert '"unit_phrase": "<sorgudaki EN SPESİFİK birim ifadesi' in out
        assert '"subunit": {"verdict"' in out
        assert "| null" in out
        assert "ÇIKTI: SADECE aşağıdaki şemaya uyan" in out

    def test_between_v1_and_v3_in_length(self):
        q, dq, p, s = _fixture()
        v1, v3, v4 = (len(build_prompt(q, dq, p, s, variant=v)) for v in (V1, V3, V4))
        assert v3 < v4 < v1

    def test_differs_from_both(self):
        q, dq, p, s = _fixture()
        a, b, c = (build_prompt(q, dq, p, s, variant=v) for v in (V1, V3, V4))
        assert c != a and c != b


class TestVariantRegistry:
    def test_get_known(self):
        assert get_variant("v1") is V1
        assert get_variant("v3") is V3
        assert get_variant("v4") is V4

    def test_unknown_raises_loudly(self):
        with pytest.raises(KeyError, match="bilinmeyen varyant"):
            get_variant("v99")

    def test_frozen(self):
        with pytest.raises(Exception):
            V1.olu_kurallar = False  # type: ignore[misc]


def test_missing_block_raises_instead_of_silent_noop():
    """Prompt ileride degisir de cikarilacak blok bulunamazsa varyant SESSIZCE
    bos islem yapmamali - yoksa 'olcum yaptik' sanip hicbir sey olcmezdik.
    Iki bayrak icin de ayri ayri gecerli."""
    from institution_resolver_v3.judge import prompt as prompt_mod

    with pytest.raises(RuntimeError, match="bulunamadi"):
        prompt_mod._apply_variant(
            "alakasiz metin", PromptVariant(name="x", sema_zorunlu_kurallar=False)
        )
    with pytest.raises(RuntimeError, match="bulunamadi"):
        prompt_mod._apply_variant("alakasiz metin", PromptVariant(name="y", sema_ornegi=False))
