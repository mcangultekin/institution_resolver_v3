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


def test_two_equal_span_exact_ambiguous() -> None:
    parents = [
        _cand("1", "SULEYMAN DEMIREL UNIVERSITESI", tsr=100.0, exact_text="suleyman demirel universitesi"),
        _cand("2", "SULEYMAN DEMIREL UNIVERSITY", tsr=100.0, exact_text="suleyman demirel university"),
    ]
    g = gate(_result(parents=parents, institution_part="suleyman demirel universitesi"), config=_CFG)
    assert g.parent.verdict == "ambiguous"
    assert g.parent.signals["reason"] == "coklu_exact"


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
    parents = [_cand("14", "EGE UNIVERSITESI", tsr=100.0, exact_text="ege universitesi")]
    subs = [
        _cand("900", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="101"),
        _cand("901", "GERIATRI BILIM DALI", tsr=100.0, exact_text="geriatri bilim dali",
              record_type="subunit", parent_id="14"),
    ]
    g = gate(_result(parents=parents, subunits=subs, unit_part="geriatri bilim dali"), config=_CFG)
    assert isinstance(g.subunit, GateDecision)
    assert g.subunit.verdict == "auto_match"  # parent'a baglanip teklesti
    assert g.subunit.matched_id == "901"
