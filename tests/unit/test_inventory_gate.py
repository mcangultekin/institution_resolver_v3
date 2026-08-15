"""Envanter modunda havuz kalitesi kapisi (jobs/inventory.py).

Kapinin uretim yoluna baglanmasi 2026-08-15 kararidir. Canli dogrulandi:
    "University of South Australia" -> University of South Alabama  öksüz: australia
    "T.C. Ticaret Bakanlığı"        -> İSTANBUL TİCARET ÜNİVERSİTESİ öksüz: bakanligi
Ikisi de 30 satirlik nokta kontrolunde bulunan hatalardi ve ikisi de artik
`review`e iniyor. Bu testler o davranisi LLM'siz sabitler.
"""

from __future__ import annotations

from institution_resolver_v3.jobs.inventory import DEFAULT_POOL_GATE, process_one_inventory
from institution_resolver_v3.judge.schema import JudgeResult
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate


def _sonuc(query, parent_ad, parent_id="1", aliases=()):
    hyp = BoundaryHypothesis(query, "", 90.0, parent_ad, parent_id)
    dq = DecomposedQuery(query, "", 90.0, parent_ad, parent_id, hypotheses=[hyp])
    p = ScoredCandidate(id=parent_id, record_type="parent", name=parent_ad,
                        raw={"id": parent_id, "aliases": list(aliases)},
                        bm25_norm=1.0, token_set_ratio=80.0)
    return ResolveResult(query=query, decomposed=dq, parents=[p], subunits=[])


def _gate_review(res, config=None):
    """Parent'i `review` yapan sahte gate -> hakem tetiklenir."""
    from institution_resolver_v3.gate.gate import GateDecision, GateResult

    return GateResult(query=res.query,
                      parent=GateDecision("review", None, 0.5, {"reason": "test"}),
                      subunit=None, unit_phrase=None)


def _judge_auto(res, client, **kw):
    return JudgeResult.model_validate(
        {"parent": {"verdict": "auto_match", "matched_id": res.parents[0].id},
         "unit_phrase": None, "subunit": None}
    )


DF = {"australia": 314, "alabama": 5, "university": 11607, "of": 19083,
      "south": 841, "afad": 2, "afet": 3, "acil": 4, "durum": 4,
      "yonetimi": 6, "baskanligi": 9}


def test_gate_downgrades_when_identity_token_missing():
    """Secilen kayit sorgunun kimlik kelimesini tasimiyorsa auto_match -> review."""
    res = _sonuc("University of South Australia", "University of South Alabama")
    rec = process_one_inventory(
        "University of South Australia", client=object(), resolve_fn=lambda q, **k: res,
        gate_fn=_gate_review, judge_fn=_judge_auto, token_df=DF,
    )
    assert rec["gate_orphan_fired"] == "1"
    assert rec["orphan_tokens"] == "australia"
    assert rec["parent_verdict"] == "review"
    assert rec["parent_id"] == "1"          # KIMLIK KORUNUR - sert no_match degil
    assert rec["pool_gate"] == DEFAULT_POOL_GATE
    assert rec["prompt_variant"] == "v4"


def test_gate_silent_when_alias_covers_identity():
    """AFAD sorgusu, kaydin alias'inda gectigi icin kapi ateşlemez."""
    res = _sonuc("AFAD", "Afet ve Acil Durum Yönetimi Başkanlığı", aliases=["AFAD"])
    rec = process_one_inventory(
        "AFAD", client=object(), resolve_fn=lambda q, **k: res,
        gate_fn=_gate_review, judge_fn=_judge_auto, token_df=DF,
    )
    assert rec["gate_orphan_fired"] == "0"
    assert rec["parent_verdict"] == "auto_match"


def test_gate_can_be_disabled():
    res = _sonuc("University of South Australia", "University of South Alabama")
    rec = process_one_inventory(
        "University of South Australia", client=object(), resolve_fn=lambda q, **k: res,
        gate_fn=_gate_review, judge_fn=_judge_auto, token_df=DF, pool_gate=None,
    )
    assert rec["parent_verdict"] == "auto_match"
    assert rec["gate_orphan_fired"] == ""


def test_gate_does_not_touch_non_auto_verdicts():
    """Hakem zaten `review` dediyse kapi bir sey degistirmez - iki kez
    cezalandirma yok; yalnizca oksuz bayragi kaydedilir."""
    def _judge_review(res, client, **kw):
        return JudgeResult.model_validate(
            {"parent": {"verdict": "review", "matched_id": res.parents[0].id},
             "unit_phrase": None, "subunit": None})

    res = _sonuc("University of South Australia", "University of South Alabama")
    rec = process_one_inventory(
        "University of South Australia", client=object(), resolve_fn=lambda q, **k: res,
        gate_fn=_gate_review, judge_fn=_judge_review, token_df=DF,
    )
    assert rec["gate_orphan_fired"] == "1"
    assert rec["parent_verdict"] == "review"
