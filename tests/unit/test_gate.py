"""gate/ birim testleri - LLM'siz, ES'siz (saf fonksiyon, resolve sonucu enjekte).

Karar OMURGASI exact_match (span>=2). bm25/kosinus KARARA GIRMEZ (yalniz gosterim).
Esik config.gate.garbage_lexical_floor'dan; testler kendi config'ini enjekte eder.
"""

from __future__ import annotations

from institution_resolver_v3.gate.gate import GateDecision, gate, score_candidate
from institution_resolver_v3.retrieve.decompose import DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate

_CFG = {"gate": {"garbage_lexical_floor": 0.55}}


def _cand(
    id: str,
    name: str,
    *,
    tsr: float = 0.0,
    exact_text: str | None = None,
    conflict: bool = False,
    bm25: float = 0.0,
    cosine: float | None = None,
    record_type: str = "parent",
    parent_id: str | None = None,
) -> ScoredCandidate:
    """exact_text verilirse exact_match=True + o metin (span testleri icin)."""
    raw: dict = {"id": id}
    if parent_id is not None:
        raw["parent_id"] = parent_id
    return ScoredCandidate(
        id=id,
        record_type=record_type,
        name=name,
        raw=raw,
        bm25_norm=bm25,
        cosine=cosine,
        token_set_ratio=tsr,
        qualifier_conflict=conflict,
        exact_match=exact_text is not None,
        exact_match_text=exact_text,
    )


def _result(
    *,
    parents: list[ScoredCandidate],
    subunits: list[ScoredCandidate] | None = None,
    institution_part: str = "ege universitesi",
    unit_part: str | None = None,
    query: str = "ege universitesi",
) -> ResolveResult:
    dq = DecomposedQuery(
        institution_part=institution_part,
        unit_part=unit_part,
        boundary_score=90.0,
        matched_parent_name=None,
        matched_parent_id=None,
    )
    return ResolveResult(query=query, decomposed=dq, parents=parents, subunits=subunits or [])


# --- score_candidate (guven skoru; bm25/kosinus girmez) ----------------------


def test_score_ignores_bm25_and_cosine() -> None:
    lo = _cand("1", "X", tsr=90.0, bm25=0.0, cosine=-0.9)
    hi = _cand("2", "X", tsr=90.0, bm25=1.0, cosine=0.99)
    assert score_candidate(lo) == score_candidate(hi)  # yalniz tsr


def test_score_exact_bonus_and_conflict() -> None:
    plain = _cand("1", "X", tsr=80.0)
    exact = _cand("2", "EGE UNI", tsr=80.0, exact_text="ege uni")  # span2 -> bonus
    assert score_candidate(exact) > score_candidate(plain)
    dirty = _cand("3", "X", tsr=80.0, conflict=True)
    assert score_candidate(dirty) < score_candidate(plain)


# --- kova atama --------------------------------------------------------------


def test_empty_parent_pool_no_match() -> None:
    g = gate(_result(parents=[]), config=_CFG)
    assert g.parent.verdict == "no_match"
    assert g.parent.matched_id is None
    assert g.subunit is None  # unit_part yok


def test_unique_exact_auto_match() -> None:
    parents = [
        _cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi"),
        _cand("99", "EGE TARIM", tsr=40.0),
    ]
    g = gate(_result(parents=parents), config=_CFG)
    assert g.parent.verdict == "auto_match"
    assert g.parent.matched_id == "14"
    assert g.parent.signals["reason"] == "tek_exact"


def test_single_token_exact_not_auto() -> None:
    # span=1 (generic tek token) -> auto YOK; exact 'guclu' sayilmaz -> exact_yok dali.
    parents = [_cand("1", "ACIBADEM ADANA", tsr=100.0, exact_text="acibadem")]
    g = gate(_result(parents=parents, institution_part="acibadem hastanesi"), config=_CFG)
    assert g.parent.verdict != "auto_match"


def test_no_exact_below_floor_no_match() -> None:
    parents = [_cand("1", "ALAKASIZ", tsr=30.0)]
    g = gate(_result(parents=parents), config=_CFG)
    assert g.parent.verdict == "no_match"
    assert g.parent.signals["reason"] == "taban_alti"


def test_no_exact_above_floor_review() -> None:
    # tsr yuksek ama exact yok -> review (#6 marj-kapili tsr-auto ertelendi).
    parents = [_cand("1", "YOZGAT BOZOK UNIVERSITESI", tsr=97.0), _cand("2", "X", tsr=50.0)]
    g = gate(_result(parents=parents), config=_CFG)
    assert g.parent.verdict == "review"
    assert g.parent.matched_id is None
    assert g.parent.signals["reason"] == "exact_yok"


def test_no_exact_review_applies_conflict_penalty_to_confidence() -> None:
    """Dalga2 #10a: confidence tek formule (score_candidate) - 'exact yok'
    dalinda da nitelik celiskisi cezasi uygulanmali, ham tsr/100 degil.
    Verdict degismiyor (review), sadece gosterilen sayi dogrulaniyor."""
    parents = [_cand("1", "YOZGAT BOZOK UNIVERSITESI", tsr=90.0, conflict=True)]
    g = gate(_result(parents=parents), config=_CFG)
    assert g.parent.verdict == "review"
    assert g.parent.confidence == score_candidate(parents[0])
    assert g.parent.confidence < 0.90  # ceza uygulanmis olmali (0.90 - 0.30 = 0.60)


def test_two_equal_span_exact_ambiguous() -> None:
    parents = [
        _cand("1", "SULEYMAN DEMIREL UNIVERSITESI", tsr=100.0, exact_text="suleyman demirel universitesi"),
        _cand("2", "SULEYMAN DEMIREL UNIVERSITY", tsr=100.0, exact_text="suleyman demirel university"),
    ]
    g = gate(_result(parents=parents, institution_part="suleyman demirel universitesi"), config=_CFG)
    assert g.parent.verdict == "ambiguous"
    assert g.parent.signals["reason"] == "coklu_exact_herhangi"


def test_parent_shorter_generic_exact_also_blocks_auto() -> None:
    """PARENT'ta HERHANGI ikinci exact auto'yu engeller (2026-07-30 kullanici karari).

    Eski davranista kazananin ICINDEKI kisa/jenerik exact ("state hospital")
    auto'yu engellemiyordu; artik engelliyor. Olculen bedel: benchmark'in ilk 150
    sorgusunda 5 karar (%3.3) auto'dan ambiguous'a duser.
    """
    parents = [
        _cand("1", "BAYBURT STATE HOSPITAL", tsr=100.0, exact_text="bayburt state hospital"),
        _cand("2", "STATE HOSPITAL", tsr=90.0, exact_text="state hospital"),
    ]
    g = gate(_result(parents=parents, institution_part="bayburt state hospital"), config=_CFG)
    assert g.parent.verdict == "ambiguous"
    assert g.parent.matched_id == "1"          # yine en spesifik aday raporlanir
    assert g.parent.signals["reason"] == "coklu_exact_herhangi"


def test_subunit_keeps_old_span_rule() -> None:
    """SUBUNIT kapsam disi: kisa/jenerik ikinci exact orada auto'yu ENGELLEMEZ."""
    parents = [_cand("1", "GAZI UNIVERSITESI", tsr=100.0, exact_text="gazi universitesi")]
    subunits = [
        _cand("10", "KARDIYOLOJI ANABILIM DALI", tsr=100.0,
              exact_text="kardiyoloji anabilim dali", parent_id="1"),
        _cand("11", "ANABILIM DALI", tsr=80.0, exact_text="anabilim dali", parent_id="1"),
    ]
    g = gate(
        _result(parents=parents, subunits=subunits,
                institution_part="gazi universitesi", unit_part="kardiyoloji anabilim dali"),
        config=_CFG,
    )
    assert g.subunit is not None
    assert g.subunit.verdict == "auto_match"
    assert g.subunit.signals["reason"] == "tek_exact"


def test_short_acronym_exact_review() -> None:
    parents = [_cand("1", "METU", tsr=100.0, exact_text="metu odtu")]
    g = gate(_result(parents=parents, institution_part="METU"), config=_CFG)
    assert g.parent.verdict == "review"
    assert g.parent.signals["reason"] == "akronim"


def test_conflict_exact_not_strong() -> None:
    # exact ama qualifier celiskisi -> guclu exact degil -> exact_yok dali (auto degil).
    parents = [_cand("1", "CAMBRIDGE UK", tsr=100.0, exact_text="cambridge uk", conflict=True)]
    g = gate(_result(parents=parents, institution_part="cambridge us"), config=_CFG)
    assert g.parent.verdict != "auto_match"


# --- subunit -----------------------------------------------------------------


def test_subunit_none_when_no_unit_phrase() -> None:
    parents = [_cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi")]
    g = gate(_result(parents=parents, unit_part=None), config=_CFG)
    assert g.subunit is None


def test_subunit_requested_but_empty_no_match() -> None:
    parents = [_cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi")]
    g = gate(_result(parents=parents, subunits=[], unit_part="geriatri"), config=_CFG)
    assert g.subunit is not None
    assert g.subunit.verdict == "no_match"
    assert g.unit_phrase == "geriatri"


def test_subunit_bound_to_chosen_parent() -> None:
    # Ayni adli iki subunit farkli parent'ta; parent=14 secilince 14 altindaki secilir.
    # (Ayni zamanda tutarlilik kapisi REGRESYON testi: parent auto + sub 14 altinda
    #  -> auto KORUNUR, _enforce_coherence bunu kapmamali.)
    parents = [_cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi")]
    subs = [
        _cand("900", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="101"),
        _cand("901", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="14"),
    ]
    g = gate(_result(parents=parents, subunits=subs, unit_part="geriatri bilim dali"), config=_CFG)
    assert isinstance(g.subunit, GateDecision)
    assert g.subunit.verdict == "auto_match"  # parent'a baglanip teklesti (auto korundu)
    assert g.subunit.matched_id == "901"


# --- P2: capraz-havuz tutarlilik (_enforce_coherence) ------------------------
# Dalga 0 (50-sorgu DENEY seti) canli ihlaller: #29 parent=review/sub=auto,
# #1 parent=ambiguous/sub=auto. Kural: subunit auto <=> parent auto + o parent altinda.


def test_coherence_parent_review_caps_subunit_auto() -> None:
    # #29 vakasi: parent exact yok ama tsr yuksek -> review (matched_id=None);
    # subunit exact -> auto secilir ama HICBIR kesin parent'a bagli degil -> review'e cekilir.
    parents = [_cand("1", "YOZGAT BOZOK UNIVERSITESI", tsr=97.0)]  # exact yok -> review
    subs = [_cand("900", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
                  record_type="subunit", parent_id="1")]
    g = gate(_result(parents=parents, subunits=subs, unit_part="geriatri bilim dali"), config=_CFG)
    assert g.parent.verdict == "review"
    assert g.subunit.verdict == "review"                       # auto -> review
    assert g.subunit.matched_id is None                        # 2026-07-30: KIMLIK onerilmez
    assert g.subunit.signals["capped_from"] == "auto_match"
    assert g.subunit.signals["reason"] == "parent_kesin_degil"


def test_coherence_parent_ambiguous_caps_subunit_auto() -> None:
    # #1 vakasi: parent gercek ikiz (ambiguous) iken subunit auto asiri-iddia.
    parents = [
        _cand("1", "SULEYMAN DEMIREL UNIVERSITESI", tsr=100.0, exact_text="suleyman demirel universitesi"),
        _cand("2", "SULEYMAN DEMIREL UNIVERSITY", tsr=100.0, exact_text="suleyman demirel university"),
    ]
    subs = [_cand("900", "TICARET HUKUKU ABD", tsr=100.0, exact_text="ticaret hukuku abd",
                  record_type="subunit", parent_id="1")]
    g = gate(_result(parents=parents, subunits=subs,
                     institution_part="suleyman demirel universitesi",
                     unit_part="ticaret hukuku abd"), config=_CFG)
    assert g.parent.verdict == "ambiguous"
    assert g.subunit.verdict == "review"
    assert g.subunit.matched_id is None                        # 2026-07-30: KIMLIK onerilmez


def test_coherence_subunit_auto_under_wrong_parent_capped() -> None:
    # parent auto=14; ama tek subunit exact 101 ALTINDA (14 altinda yok) -> auto ama
    # yanlis parent altinda -> review'e cekilir (parent auto olsa BILE).
    parents = [_cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi")]
    subs = [_cand("900", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
                  record_type="subunit", parent_id="101")]
    g = gate(_result(parents=parents, subunits=subs, unit_part="geriatri bilim dali"), config=_CFG)
    assert g.parent.verdict == "auto_match" and g.parent.matched_id == "14"
    assert g.subunit.verdict == "review"
    assert g.subunit.matched_id is None                        # 2026-07-30: KIMLIK onerilmez
    assert g.subunit.signals["parent_verdict"] == "auto_match"


def test_coherence_ambiguous_subunit_loses_id_when_parent_not_auto() -> None:
    """2026-07-30 (kullanici karari): kural sadece auto->review dususunu degil,
    subunit'in KENDI review/ambiguous verdict'ini de kapsamali - iki adayli bir
    subunit havuzunda (esit span exact -> ambiguous) parent auto_match degilse,
    o iki adaydan HANGISININ onerilecegi zaten anlamsiz (parent bilinmeden
    subunit kimligi tamamlanmaz)."""
    parents = [_cand("1", "YOZGAT BOZOK UNIVERSITESI", tsr=97.0)]  # exact yok -> review
    subs = [
        _cand("900", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="1"),
        _cand("901", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="14"),
    ]
    g = gate(_result(parents=parents, subunits=subs, unit_part="geriatri bilim dali"), config=_CFG)
    assert g.parent.verdict == "review"
    assert g.subunit.verdict == "ambiguous"       # kendi ici zaten ambiguous, degismiyor
    assert g.subunit.matched_id is None           # ama artik KIMLIK onerilmiyor
