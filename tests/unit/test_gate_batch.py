"""Gate-only batch testleri - resolve/gate ENJEKTE edilir (ES'ye gidilmez, LLM YOK)."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace as NS

from institution_resolver_v3.eval.gate_batch import FIELDNAMES, process_one_gate, run_gate_batch


def _resolve(query, size=5):
    return NS(
        query=query,
        parents=[NS(id="P1", name="EGE UNIVERSITESI"), NS(id="P2", name="X UNI")],
        subunits=[NS(id="S1", name="TIP FAKULTESI")],
    )


def _signals(**kw):
    base = {"tsr": 95.0, "exact_match": True, "exact_span": 2, "qualifier_conflict": False,
            "bm25_norm": 0.8, "cosine": 0.5, "reason": "tek_exact"}
    base.update(kw)
    return base


def _gate_auto(res):
    return NS(
        query=res.query,
        # auto_match: candidates BILEREK bos (2026-08-21 karari)
        parent=NS(
            verdict="auto_match", matched_id="P1", confidence=0.95, signals=_signals(),
            candidates=[],
        ),
        subunit=NS(
            verdict="auto_match", matched_id="S1", confidence=0.9, signals=_signals(),
            candidates=[],
        ),
        unit_phrase="tip fakultesi",
    )


def _gate_ambiguous(res):
    return NS(
        query=res.query,
        parent=NS(
            verdict="ambiguous", matched_id="P1", confidence=0.7,
            signals=_signals(reason="coklu_exact"), candidates=["P1", "P2"],
        ),
        subunit=None,
        unit_phrase=None,
    )


def _gate_no_match(res):
    return NS(
        query=res.query,
        parent=NS(verdict="no_match", matched_id=None, confidence=0.1,
                  signals={"reason": "taban_alti"}, candidates=[]),
        subunit=None,
        unit_phrase=None,
    )


def _boom_gate(res):
    raise RuntimeError("es koptu")


def test_process_one_gate_auto_writes_signals():
    rec = process_one_gate("Ege Tıp", resolve_fn=_resolve, gate_fn=_gate_auto)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "auto_match"
    assert rec["parent_id"] == "P1"
    assert rec["parent_name"] == "EGE UNIVERSITESI"
    assert rec["parent_tsr"] == "95.0"
    assert rec["parent_exact_match"] == "True"
    assert rec["subunit_verdict"] == "auto_match"
    assert rec["subunit_name"] == "TIP FAKULTESI"
    d = json.loads(rec["result_json"])
    assert d["parent"]["signals"]["reason"] == "tek_exact"
    assert rec["candidates"] == ""  # auto_match: oneri BOS


def test_ambiguous_writes_candidates_cell_without_touching_parent_id():
    rec = process_one_gate("Ege Tıp", resolve_fn=_resolve, gate_fn=_gate_ambiguous)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "ambiguous"
    # parent_id/parent_name DOKUNULMADI - eskisi gibi gate'in secimini tasir
    assert rec["parent_id"] == "P1"
    assert rec["parent_name"] == "EGE UNIVERSITESI"
    # "oneri" SAF EKLENTI, tek hucrede virgulle ayrilmis "id:Ad"
    assert rec["candidates"] == "P1:EGE UNIVERSITESI, P2:X UNI"


def test_no_match_is_not_error_and_no_subunit_signals():
    rec = process_one_gate("çöp metin", resolve_fn=_resolve, gate_fn=_gate_no_match)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "no_match"
    assert rec["parent_id"] == ""
    assert rec["candidates"] == ""  # no_match: oneri BOS
    assert rec["subunit_verdict"] == ""  # subunit yok (unit_part yok)
    assert rec["subunit_tsr"] == ""


def test_process_one_gate_isolates_errors():
    rec = process_one_gate("boom", resolve_fn=_resolve, gate_fn=_boom_gate)
    assert rec["status"] == "error" and "es koptu" in rec["error"]


def test_run_gate_batch_writes_csv(tmp_path):
    out = tmp_path / "res.csv"
    summary = run_gate_batch(["a", "b"], out, resolve_fn=_resolve, gate_fn=_gate_auto)
    assert summary["ok"] == 2 and summary["error"] == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert list(rows[0].keys()) == FIELDNAMES
    assert rows[0]["parent_verdict"] == "auto_match"
