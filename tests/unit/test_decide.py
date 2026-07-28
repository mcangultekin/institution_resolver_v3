"""decide/ birim testleri - gate/judge/resolve ENJEKTE edilir (ES/Ollama'ya gidilmez).

Kural: gate parent VE (subunit yoksa ya da subunit) ikisi de auto_match ise LLM
HIC CAGRILMAZ (decided_by='gate'); herhangi biri auto degilse sorgunun TAMAMI
judge()'a gider, nihai karar (parent+subunit) judge'den gelir (decided_by='judge')."""

from __future__ import annotations

from types import SimpleNamespace as NS

from institution_resolver_v3.decide.decide import decide


def _gate_decision(verdict="auto_match", matched_id="P1", signals=None):
    return NS(verdict=verdict, matched_id=matched_id, confidence=0.9, signals=signals or {})


def _gate_result(parent, subunit):
    return NS(query="q", parent=parent, subunit=subunit, unit_phrase="birim" if subunit else None)


def _resolve_fn(query, size=5):
    return NS(query=query, parents=[NS(id="P1", name="EGE UNI")], subunits=[NS(id="S1", name="TIP")])


def _judge_result(parent_verdict="auto_match", parent_id="P1", subunit=None, unit_phrase=None):
    return NS(
        parent=NS(verdict=parent_verdict, matched_id=parent_id),
        subunit=subunit,
        unit_phrase=unit_phrase,
    )


def _boom_judge(res, client):
    raise AssertionError("judge_fn cagrilmamali idi - gate yetmis olmaliydi")


def test_gate_sufficient_no_llm_call():
    g = _gate_result(_gate_decision("auto_match", "P1"), _gate_decision("auto_match", "S1"))
    d = decide(
        "ege uni tip",
        client=None,
        resolve_fn=_resolve_fn,
        gate_fn=lambda res, config=None: g,
        judge_fn=_boom_judge,
    )
    assert d.parent.verdict == "auto_match" and d.parent.decided_by == "gate"
    assert d.subunit.verdict == "auto_match" and d.subunit.decided_by == "gate"
    assert d.judge is None
    assert d.gate is g  # gate her zaman saklanir


def test_gate_no_subunit_phrase_no_llm_call():
    g = _gate_result(_gate_decision("auto_match", "P1"), None)
    d = decide(
        "ege uni", client=None, resolve_fn=_resolve_fn,
        gate_fn=lambda res, config=None: g, judge_fn=_boom_judge,
    )
    assert d.parent.decided_by == "gate"
    assert d.subunit is None
    assert d.judge is None


def test_parent_not_auto_escalates_to_judge():
    g = _gate_result(_gate_decision("review", None), None)
    j = _judge_result(parent_verdict="auto_match", parent_id="P1")
    d = decide(
        "belirsiz", client=None, resolve_fn=_resolve_fn,
        gate_fn=lambda res, config=None: g, judge_fn=lambda res, client: j,
    )
    assert d.parent.decided_by == "judge"
    assert d.parent.verdict == "auto_match" and d.parent.matched_id == "P1"
    assert d.judge is j
    assert d.gate is g  # gate sinyalleri kaybolmaz, LLM'e dusse bile saklanir


def test_subunit_not_auto_escalates_whole_query():
    # parent auto ama subunit review -> TUM sorgu LLM'e (kismi devir yok).
    g = _gate_result(_gate_decision("auto_match", "P1"), _gate_decision("review", None))
    j = _judge_result(
        parent_verdict="auto_match", parent_id="P1",
        subunit=NS(verdict="auto_match", matched_id="S1"), unit_phrase="tip",
    )
    d = decide(
        "ege uni belirsiz birim", client=None, resolve_fn=_resolve_fn,
        gate_fn=lambda res, config=None: g, judge_fn=lambda res, client: j,
    )
    assert d.parent.decided_by == "judge"
    assert d.subunit.decided_by == "judge"
    assert d.subunit.matched_id == "S1"


def test_judge_subunit_none_stays_none():
    g = _gate_result(_gate_decision("no_match", None), None)
    j = _judge_result(parent_verdict="no_match", parent_id=None, subunit=None, unit_phrase=None)
    d = decide(
        "cop metin", client=None, resolve_fn=_resolve_fn,
        gate_fn=lambda res, config=None: g, judge_fn=lambda res, client: j,
    )
    assert d.subunit is None
    assert d.parent.verdict == "no_match" and d.parent.matched_id is None
