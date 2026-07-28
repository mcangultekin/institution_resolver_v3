"""Hibrit (gate+judge) batch testleri - decide_fn ENJEKTE edilir (ES/Ollama'ya gidilmez)."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace as NS

from institution_resolver_v3.eval.decide_batch import FIELDNAMES, process_one_decide, run_decide_batch


def _gate_decision(verdict, matched_id, reason):
    return NS(verdict=verdict, matched_id=matched_id, confidence=0.9, signals={"reason": reason, "tsr": 90.0})


def _decide_gate_only(query, client, size=5):
    res = NS(parents=[NS(id="P1", name="EGE UNI")], subunits=[NS(id="S1", name="TIP")])
    g = NS(
        parent=_gate_decision("auto_match", "P1", "tek_exact"),
        subunit=_gate_decision("auto_match", "S1", "tek_exact"),
    )
    return NS(
        query=query,
        parent=NS(verdict="auto_match", matched_id="P1", decided_by="gate"),
        subunit=NS(verdict="auto_match", matched_id="S1", decided_by="gate"),
        unit_phrase="tip",
        gate=g,
        judge=None,
        resolve_result=res,
    )


def _decide_escalated(query, client, size=5):
    res = NS(parents=[NS(id="P1", name="EGE UNI")], subunits=[])
    g = NS(
        parent=_gate_decision("review", None, "exact_yok"),
        subunit=None,
    )
    return NS(
        query=query,
        parent=NS(verdict="auto_match", matched_id="P1", decided_by="judge"),
        subunit=None,
        unit_phrase=None,
        gate=g,
        judge=NS(parent=NS(verdict="auto_match", matched_id="P1"), subunit=None, unit_phrase=None),
        resolve_result=res,
    )


def _boom(query, client, size=5):
    raise RuntimeError("baglanti koptu")


def test_gate_decided_row_has_no_llm_and_gate_signals():
    rec = process_one_decide("ege uni tip", client=None, decide_fn=_decide_gate_only)
    assert rec["status"] == "ok"
    assert rec["decided_by"] == "gate"
    assert rec["parent_verdict"] == "auto_match" and rec["parent_id"] == "P1"
    assert rec["parent_name"] == "EGE UNI"
    assert rec["gate_parent_verdict"] == "auto_match"
    assert rec["gate_parent_tsr"] == "90.0"
    assert rec["gate_subunit_verdict"] == "auto_match"


def test_escalated_row_still_carries_gate_signals():
    # decided_by=judge OLSA BILE gate sinyalleri CSV'de - kullanici istegi (denetim).
    rec = process_one_decide("belirsiz", client=None, decide_fn=_decide_escalated)
    assert rec["decided_by"] == "judge"
    assert rec["parent_verdict"] == "auto_match"
    assert rec["gate_parent_verdict"] == "review"  # gate ne dusunuyordu, kayboldu degil
    assert rec["gate_parent_reason"] == "exact_yok"
    d = json.loads(rec["result_json"])
    assert d["gate"]["parent"]["verdict"] == "review"


def test_process_one_decide_isolates_errors():
    rec = process_one_decide("boom", client=None, decide_fn=_boom)
    assert rec["status"] == "error" and "baglanti" in rec["error"]


def test_run_decide_batch_writes_csv(tmp_path):
    out = tmp_path / "res.csv"
    summary = run_decide_batch(["a", "b"], client=None, out_path=out, decide_fn=_decide_gate_only)
    assert summary["ok"] == 2 and summary["error"] == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert list(rows[0].keys()) == FIELDNAMES
    assert rows[0]["decided_by"] == "gate"
