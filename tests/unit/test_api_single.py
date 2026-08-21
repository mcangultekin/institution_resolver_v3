"""Tekli-sorgu API endpoint testleri - resolve/gate/judge/decide ENJEKTE edilir
(ES/Ollama'ya gidilmez, ayni ilke tests/unit/test_batch.py). `/health` burada
YOK - o create_app()'in lifespan'inda gercek embedding modelini isitip ES/Ollama'ya
canli baglaniyor, unit test kapsamimizin disinda (bkz. plan)."""

from __future__ import annotations

from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient

from institution_resolver_v3.api import deps
from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.api.routers import batch as batch_router
from institution_resolver_v3.api.routers import single as single_router
from institution_resolver_v3.judge.client import LlmError
from institution_resolver_v3.judge.judge import JudgeValidationError


def _fake_resolve(query, size=5, **kw):  # **kw: with_cosine gibi gosterim bayraklarini yutar
    parent = NS(
        id="P1", name="EGE UNIVERSITESI", bm25_norm=0.9, cosine=0.5,
        token_set_ratio=95.0, exact_match=True, passed_parent_filter=None,
        qualifier_conflict=False, raw={},
    )
    parent2 = NS(  # ambiguous/oneri testlerinde rakip aday
        id="P2", name="EGE UNIVERSITY", bm25_norm=0.85, cosine=0.45,
        token_set_ratio=90.0, exact_match=True, passed_parent_filter=None,
        qualifier_conflict=False, raw={},
    )
    subunit = NS(
        id="S1", name="TIP FAKULTESI", bm25_norm=0.8, cosine=0.4,
        token_set_ratio=90.0, exact_match=True, passed_parent_filter=True,
        qualifier_conflict=False, raw={"parent_name": "EGE UNIVERSITESI"},
    )
    decomposed = NS(
        institution_part="ege universitesi", unit_part="tip fakultesi",
        boundary_score=95.0, matched_parent_name="EGE UNIVERSITESI",
        matched_parent_id="P1", hypotheses=[],
    )
    return NS(query=query, decomposed=decomposed, parents=[parent, parent2], subunits=[subunit])


def _fake_gate(result):
    parent_d = NS(
        verdict="auto_match", matched_id="P1", confidence=0.95, signals={"tsr": 95},
        candidates=[],
    )
    subunit_d = NS(
        verdict="auto_match", matched_id="S1", confidence=0.9, signals={"tsr": 90},
        candidates=[],
    )
    return NS(query=result.query, parent=parent_d, subunit=subunit_d, unit_phrase="tip fakultesi")


def _fake_gate_ambiguous(result):
    parent_d = NS(
        verdict="ambiguous", matched_id="P1", confidence=0.7, signals={"tsr": 90},
        candidates=["P1", "P2"],
    )
    return NS(query=result.query, parent=parent_d, subunit=None, unit_phrase=None)


def _fake_judge_auto(result, client):
    return NS(
        parent=NS(verdict="auto_match", matched_id="P1"),
        subunit=NS(verdict="auto_match", matched_id="S1"),
        unit_phrase="tip fakultesi",
    )


def _fake_judge_ambiguous(result, client):
    return NS(
        parent=NS(verdict="ambiguous", matched_id="P1"),
        subunit=NS(verdict="auto_match", matched_id="S1"),
        unit_phrase="tip fakultesi",
    )


def _fake_judge_validation_error(result, client):
    raise JudgeValidationError("çelişkili cevap")


def _fake_judge_llm_error(result, client):
    raise LlmError("baglanti koptu")


def _fake_decide_gate_only(query, client, size=5, **kw):  # **kw: with_cosine gibi gosterim bayraklarini yutar
    result = _fake_resolve(query, size=size)
    g = _fake_gate(result)
    return NS(
        query=query,
        parent=NS(verdict="auto_match", matched_id="P1", decided_by="gate"),
        subunit=NS(verdict="auto_match", matched_id="S1", decided_by="gate"),
        unit_phrase="tip fakultesi",
        gate=g,
        judge=None,
        resolve_result=result,
    )


def _fake_decide_ambiguous_by_judge(query, client, size=5, **kw):
    """Gate belirsiz -> LLM'e dustu -> judge da ambiguous dedi ama TEK bir
    matched_id verdi. "Oneri" hucresi bu tek adayi tasimali (2026-08-21)."""
    result = _fake_resolve(query, size=size)
    g = NS(
        query=result.query,
        parent=NS(
            verdict="review", matched_id=None, confidence=0.5, signals={"tsr": 80},
            candidates=[],
        ),
        subunit=None,
        unit_phrase=None,
    )
    return NS(
        query=query,
        parent=NS(verdict="ambiguous", matched_id="P1", decided_by="judge"),
        subunit=None,
        unit_phrase=None,
        gate=g,
        judge=NS(parent=NS(verdict="ambiguous", matched_id="P1"), subunit=None, unit_phrase=None),
        resolve_result=result,
    )


def _fake_decide_error(query, client, size=5, **kw):  # **kw: with_cosine gibi gosterim bayraklarini yutar
    raise JudgeValidationError("çelişkili cevap")


def _make_app(*, judge_fn=_fake_judge_auto, decide_fn=_fake_decide_gate_only) -> FastAPI:
    app = FastAPI()
    app.include_router(single_router.router)
    app.include_router(batch_router.router)
    app.state.ollama_client = NS()  # fake'ler client'i kullanmiyor
    app.state.job_manager = JobManager()
    app.dependency_overrides[deps.get_resolve_fn] = lambda: _fake_resolve
    app.dependency_overrides[deps.get_gate_fn] = lambda: _fake_gate
    app.dependency_overrides[deps.get_judge_fn] = lambda: judge_fn
    app.dependency_overrides[deps.get_decide_fn] = lambda: decide_fn
    return app


def test_match_ok():
    client = TestClient(_make_app())
    r = client.post("/match", json={"query": "ege universitesi tip fakultesi", "top": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["parents"][0]["id"] == "P1"
    assert body["subunits"][0]["id"] == "S1"
    assert body["subunits"][0]["parent_name"] == "EGE UNIVERSITESI"


def test_gate_ok():
    client = TestClient(_make_app())
    r = client.post("/gate", json={"query": "ege universitesi tip fakultesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["verdict"] == "auto_match"
    assert body["parent"]["matched_id"] == "P1"
    assert body["parent"]["name"] == "EGE UNIVERSITESI"
    assert body["subunit"]["name"] == "TIP FAKULTESI"
    # auto_match: "oneri" BILEREK bos (2026-08-21 karari)
    assert body["parent"]["candidates"] == []
    assert body["subunit"]["candidates"] == []


def test_gate_ambiguous_exposes_candidates_without_touching_matched_id():
    app = _make_app()
    app.dependency_overrides[deps.get_gate_fn] = lambda: _fake_gate_ambiguous
    client = TestClient(app)
    r = client.post("/gate", json={"query": "ege universitesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["verdict"] == "ambiguous"
    # matched_id/name DOKUNULMADI - eskisi gibi gate'in secimini tasir
    assert body["parent"]["matched_id"] == "P1"
    assert body["parent"]["name"] == "EGE UNIVERSITESI"
    # "oneri" SAF EKLENTI
    cand_ids = [c["id"] for c in body["parent"]["candidates"]]
    assert cand_ids == ["P1", "P2"]


def test_judge_ok():
    client = TestClient(_make_app(judge_fn=_fake_judge_auto))
    r = client.post("/judge", json={"query": "ege universitesi tip fakultesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["verdict"] == "auto_match"
    assert body["parent"]["name"] == "EGE UNIVERSITESI"
    # auto_match: "oneri" BILEREK bos
    assert body["parent"]["candidates"] == []


def test_judge_ambiguous_exposes_candidates_without_touching_matched_id():
    client = TestClient(_make_app(judge_fn=_fake_judge_ambiguous))
    r = client.post("/judge", json={"query": "ege universitesi tip fakultesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["verdict"] == "ambiguous"
    assert body["parent"]["matched_id"] == "P1"  # DOKUNULMADI
    cand_ids = [c["id"] for c in body["parent"]["candidates"]]
    assert cand_ids == ["P1"]  # judge'in kendi tek adayi, ek olarak
    # subunit'e HIC dokunulmadi (parent-only, kullanici karari)
    assert body["subunit"]["candidates"] == []


def test_judge_validation_error_maps_to_502():
    client = TestClient(_make_app(judge_fn=_fake_judge_validation_error))
    r = client.post("/judge", json={"query": "x"})
    assert r.status_code == 502


def test_judge_llm_error_maps_to_502():
    client = TestClient(_make_app(judge_fn=_fake_judge_llm_error))
    r = client.post("/judge", json={"query": "x"})
    assert r.status_code == 502


def test_decide_ok_gate_only():
    client = TestClient(_make_app(decide_fn=_fake_decide_gate_only))
    r = client.post("/decide", json={"query": "ege universitesi tip fakultesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["decided_by"] == "gate"
    assert body["parent"]["matched_id"] == "P1"
    assert body["gate"]["parent"]["verdict"] == "auto_match"
    # auto_match: "oneri" BILEREK bos
    assert body["parent"]["candidates"] == []


def test_decide_ambiguous_by_judge_exposes_candidates_without_touching_matched_id():
    client = TestClient(_make_app(decide_fn=_fake_decide_ambiguous_by_judge))
    r = client.post("/decide", json={"query": "ege universitesi tip fakultesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"]["decided_by"] == "judge"
    assert body["parent"]["verdict"] == "ambiguous"
    # matched_id DOKUNULMADI - judge'in verdigi degeri tasir
    assert body["parent"]["matched_id"] == "P1"
    # "oneri" SAF EKLENTI - judge'in TEK adayi, ek olarak
    cand_ids = [c["id"] for c in body["parent"]["candidates"]]
    assert cand_ids == ["P1"]


def test_decide_error_maps_to_502():
    client = TestClient(_make_app(decide_fn=_fake_decide_error))
    r = client.post("/decide", json={"query": "x"})
    assert r.status_code == 502
