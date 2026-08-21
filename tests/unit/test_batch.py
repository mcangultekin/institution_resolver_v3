"""F5 batch motoru testleri - resolve/judge ENJEKTE edilir (ES/Ollama'ya gidilmez)."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace as NS

from institution_resolver_v3.eval.batch import FIELDNAMES, process_one, run_batch
from institution_resolver_v3.judge.client import LlmError
from institution_resolver_v3.judge.judge import JudgeValidationError


def _resolve(query, size=5):
    # res.query'yi tasi ki sahte hakem sorguya gore dallanabilsin
    return NS(
        query=query,
        parents=[NS(id="P1", name="EGE UNIVERSITESI"), NS(id="P2", name="X UNI")],
        subunits=[NS(id="S1", name="TIP FAKULTESI")],
    )


def _judge_auto(res, client):
    return NS(
        parent=NS(verdict="auto_match", matched_id="P1"),
        subunit=NS(verdict="auto_match", matched_id="S1"),
        unit_phrase="tip fakultesi",
    )


def _judge_nomatch(res, client):
    return NS(parent=NS(verdict="no_match", matched_id=None), subunit=None, unit_phrase=None)


def _judge_ambiguous(res, client):
    return NS(parent=NS(verdict="ambiguous", matched_id="P1"), subunit=None, unit_phrase=None)


def _judge_branchy(res, client):
    if res.query == "boom":
        raise LlmError("baglanti koptu")
    if res.query == "celis":
        raise JudgeValidationError("çelişkili cevap")
    return NS(parent=NS(verdict="auto_match", matched_id="P1"), subunit=None, unit_phrase=None)


def test_process_one_ok_full():
    rec = process_one("Ege Tıp", client=None, resolve_fn=_resolve, judge_fn=_judge_auto)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "auto_match"
    assert rec["parent_id"] == "P1"
    assert rec["parent_name"] == "EGE UNIVERSITESI"
    assert rec["subunit_verdict"] == "auto_match"
    assert rec["subunit_name"] == "TIP FAKULTESI"
    assert rec["unit_phrase"] == "tip fakultesi"
    d = json.loads(rec["result_json"])
    assert d["parent"]["matched_id"] == "P1" and d["subunit"]["matched_id"] == "S1"
    assert rec["candidates"] == ""  # auto_match: oneri BOS


def test_ambiguous_writes_candidates_cell_without_touching_parent_id():
    rec = process_one("belirsiz uni", client=None, resolve_fn=_resolve, judge_fn=_judge_ambiguous)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "ambiguous"
    # parent_id/parent_name DOKUNULMADI - judge'in verdigi degeri tasir
    assert rec["parent_id"] == "P1"
    assert rec["parent_name"] == "EGE UNIVERSITESI"
    # "oneri" SAF EKLENTI - judge'in TEK adayi, ek olarak
    assert rec["candidates"] == "P1:EGE UNIVERSITESI"


def test_no_match_is_not_error():
    # no_match/review/ambiguous HATA DEĞİL - status=ok, verdict alaninda yazilir.
    rec = process_one("çöp metin", client=None, resolve_fn=_resolve, judge_fn=_judge_nomatch)
    assert rec["status"] == "ok"
    assert rec["parent_verdict"] == "no_match"
    assert rec["parent_id"] == ""  # eslesme yok -> id bos
    assert rec["subunit_verdict"] == ""  # subunit sorguda istenmedi (None)
    assert json.loads(rec["result_json"])["subunit"] is None


def test_process_one_isolates_errors():
    rec = process_one("boom", client=None, resolve_fn=_resolve, judge_fn=_judge_branchy)
    assert rec["status"] == "error" and "baglanti" in rec["error"]
    rec2 = process_one("celis", client=None, resolve_fn=_resolve, judge_fn=_judge_branchy)
    assert rec2["status"] == "error" and "çelişkili" in rec2["error"]


def test_run_batch_writes_csv_and_isolates(tmp_path):
    out = tmp_path / "res.csv"
    summary = run_batch(
        ["a", "boom", "b"], client=None, out_path=out,
        resolve_fn=_resolve, judge_fn=_judge_branchy,
    )
    assert summary["ok"] == 2 and summary["error"] == 1 and summary["total_written"] == 3
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["status"] for r in rows] == ["ok", "error", "ok"]
    assert list(rows[0].keys()) == FIELDNAMES  # sema aynen


def test_resume_skips_done(tmp_path):
    out = tmp_path / "res.csv"
    run_batch(["a", "b"], None, out, resolve_fn=_resolve, judge_fn=_judge_branchy)
    summary = run_batch(
        ["a", "b", "c"], None, out, resolve_fn=_resolve, judge_fn=_judge_branchy, resume=True
    )
    assert summary["skipped"] == 2 and summary["total_written"] == 1
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["query"] for r in rows] == ["a", "b", "c"]  # c eklendi, a/b tekrar yazilmadi


def test_limit_caps_input(tmp_path):
    out = tmp_path / "res.csv"
    summary = run_batch(
        ["a", "b", "c", "d"], None, out, resolve_fn=_resolve, judge_fn=_judge_branchy, limit=2
    )
    assert summary["total_written"] == 2
