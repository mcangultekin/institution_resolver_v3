"""Hibrit batch: once gate (LLM'siz), auto_match vermezse (parent VEYA subunit)
sorgunun TAMAMI hakeme (LLM) devredilir - decide/decide.py cekirdegini kullanir.

Amac: F5 batch'in olcek sorununu (438k satir aylar surer, bkz. DURUM 6c) gate'in
ucuzlugundan yararlanarak azaltmak - LLM sadece gate'in emin OLMADIGI satirlara
harcanir. Gate sinyalleri HER SATIRDA (decided_by=judge olsa bile) CSV'ye yazilir
- hangi satirin neden LLM'e dustugu sonradan denetlenebilsin diye (kullanici
istegi). Ayni satir-bazli hata izolasyonu ilkesi (eval/batch.py); CSV
yazim/resume/limit mekanigi eval/csv_runner.py'de (3 batch turu ortak)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from institution_resolver_v3.decide.decide import DecideResult
from institution_resolver_v3.decide.decide import decide as _decide
from institution_resolver_v3.eval.csv_runner import ProgressFn, run_csv_batch
from institution_resolver_v3.gate.gate import GateDecision
from institution_resolver_v3.judge.client import LlmError
from institution_resolver_v3.judge.judge import JudgeValidationError

FIELDNAMES = [
    "query",
    "status",  # ok | error
    "decided_by",  # gate | judge - LLM bu satira harcandi mi
    "parent_verdict",
    "parent_id",
    "parent_name",
    # "Oneri" (2026-08-21 karari): SAF EKLENTI - parent_id/parent_name'e
    # DOKUNMAZ. Final karar review/ambiguous ise "id:Ad, id:Ad" (gate'in
    # candidates listesi ya da judge'in tek adayi - kim karar verdiyse
    # oradan); auto_match/no_match/hata satirlarinda BOS.
    "candidates",
    "subunit_verdict",
    "subunit_id",
    "subunit_name",
    "unit_phrase",
    # gate sinyalleri - decided_by=judge olsa bile HER ZAMAN doldurulur (denetim:
    # bu satir neden gate'te durmayip LLM'e dustu?)
    "gate_parent_verdict",
    "gate_parent_confidence",
    "gate_parent_tsr",
    "gate_parent_exact_match",
    "gate_parent_exact_span",
    "gate_parent_qualifier_conflict",
    "gate_parent_bm25",
    "gate_parent_cosine",
    "gate_parent_reason",
    "gate_subunit_verdict",
    "gate_subunit_confidence",
    "gate_subunit_tsr",
    "gate_subunit_exact_match",
    "gate_subunit_exact_span",
    "gate_subunit_qualifier_conflict",
    "gate_subunit_bm25",
    "gate_subunit_cosine",
    "gate_subunit_reason",
    "error",
    "elapsed_s",  # decide() tek cagri - resolve/gate/llm ayrimi yok (bkz. asagi not)
    "result_json",
]


def _name_of(pool: list, matched_id: str | None) -> str:
    if matched_id is None:
        return ""
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else ""


_SUGGESTIBLE = ("review", "ambiguous")


def _decide_candidates_cell(d: DecideResult, pool: list) -> str:
    """Final karar review/ambiguous ise "oneri" hucresini doldurur - kaynak
    kimin karar verdigine gore degisir: `decided_by=gate` ise gate'in kendi
    candidates listesi (bkz. gate.gate.py); `decided_by=judge` ise judge'in
    zaten verdigi TEK matched_id (2026-08-21 karari, SAF EKLENTI)."""
    if d.parent.verdict not in _SUGGESTIBLE:
        return ""
    if d.parent.decided_by == "gate":
        ids = d.gate.parent.candidates
    else:
        ids = [d.parent.matched_id] if d.parent.matched_id else []
    by_id = {c.id: c.name for c in pool}
    return ", ".join(f"{cid}:{by_id.get(cid, '')}" for cid in ids)


def _gate_signal_cols(prefix: str, d: GateDecision | None) -> dict[str, str]:
    s = d.signals if d is not None else {}
    cosine = s.get("cosine")
    return {
        f"{prefix}_verdict": d.verdict if d is not None else "",
        f"{prefix}_confidence": f"{d.confidence:.3f}" if d is not None else "",
        f"{prefix}_tsr": str(s.get("tsr", "")) if "tsr" in s else "",
        f"{prefix}_exact_match": str(s.get("exact_match", "")) if "exact_match" in s else "",
        f"{prefix}_exact_span": str(s.get("exact_span", "")) if "exact_span" in s else "",
        f"{prefix}_qualifier_conflict": (
            str(s.get("qualifier_conflict", "")) if "qualifier_conflict" in s else ""
        ),
        f"{prefix}_bm25": str(s.get("bm25_norm", "")) if "bm25_norm" in s else "",
        f"{prefix}_cosine": "" if cosine is None else str(cosine),
        f"{prefix}_reason": str(s.get("reason", "")),
    }


def process_one_decide(
    query: str,
    client: Any,
    *,
    decide_fn: Callable = _decide,
    top: int = 5,
) -> dict[str, str]:
    """Tek sorgu icin decide() (gate + gerekirse LLM); FIELDNAMES semasinda kayit.

    decide_fn ENJEKTE edilebilir (test ES/Ollama'ya gitmesin diye, bkz. batch.py
    ayni ilke). `elapsed_s` decide()'in TEK cagrisinin toplam suresidir -
    resolve/gate/llm alt-kirilimi decide() disariya ayrik zaman dondurmedigi
    icin burada YOK (yanlis hassasiyet vermemek icin uydurulmadi); `decided_by`
    zaten LLM'in devreye girip girmedigini soyluyor."""
    rec = {k: "" for k in FIELDNAMES}
    rec["query"] = query
    t0 = time.time()
    try:
        d: DecideResult = decide_fn(query, client, size=top)
        rec["elapsed_s"] = f"{time.time() - t0:.2f}"
        rec["status"] = "ok"
        rec["decided_by"] = d.parent.decided_by
        rec["parent_verdict"] = d.parent.verdict
        rec["parent_id"] = d.parent.matched_id or ""
        rec["parent_name"] = _name_of(d.resolve_result.parents, d.parent.matched_id)
        rec["candidates"] = _decide_candidates_cell(d, d.resolve_result.parents)
        if d.subunit is not None:
            rec["subunit_verdict"] = d.subunit.verdict
            rec["subunit_id"] = d.subunit.matched_id or ""
            rec["subunit_name"] = _name_of(d.resolve_result.subunits, d.subunit.matched_id)
        rec["unit_phrase"] = d.unit_phrase or ""
        rec.update(_gate_signal_cols("gate_parent", d.gate.parent))
        rec.update(_gate_signal_cols("gate_subunit", d.gate.subunit))
        rec["result_json"] = json.dumps(
            {
                "decided_by": d.parent.decided_by,
                "parent": {
                    "verdict": d.parent.verdict,
                    "matched_id": d.parent.matched_id,
                    "name": rec["parent_name"],
                },
                "subunit": (
                    None
                    if d.subunit is None
                    else {
                        "verdict": d.subunit.verdict,
                        "matched_id": d.subunit.matched_id,
                        "name": rec["subunit_name"],
                    }
                ),
                "unit_phrase": d.unit_phrase,
                "gate": {
                    "parent": {"verdict": d.gate.parent.verdict, "signals": d.gate.parent.signals},
                    "subunit": (
                        None
                        if d.gate.subunit is None
                        else {
                            "verdict": d.gate.subunit.verdict,
                            "signals": d.gate.subunit.signals,
                        }
                    ),
                },
            },
            ensure_ascii=False,
        )
    except (JudgeValidationError, LlmError) as exc:
        rec["status"] = "error"
        rec["error"] = str(exc)[:300]
    except Exception as exc:  # noqa: BLE001 - satir izolasyonu; batch surmeli
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return rec


def run_decide_batch(
    queries: Iterable[str],
    client: Any,
    out_path: str | Path,
    *,
    decide_fn: Callable = _decide,
    top: int = 5,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    """`queries`'i decide()'dan gecirip `out_path`'e (CSV) yazar (hibrit:
    gate auto_match vermezse LLM devreye girer). `max_workers>1`: LLM'e dusen
    satirlar es-zamanli cagrilir (bkz. csv_runner.run_csv_batch docstring)."""

    def _proc(query: str) -> dict[str, str]:
        return process_one_decide(query, client, decide_fn=decide_fn, top=top)

    return run_csv_batch(
        queries,
        out_path,
        FIELDNAMES,
        _proc,
        limit=limit,
        resume=resume,
        on_progress=on_progress,
        max_workers=max_workers,
    )
