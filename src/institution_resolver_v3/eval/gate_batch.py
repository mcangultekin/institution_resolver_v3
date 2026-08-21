"""Gate-only batch: bir CSV'deki kurum ifadelerini resolve->gate zincirinden
gecirir (LLM YOK). Amac: olcek testi/on-triyaj - E4B hakem ~20-50 s/sorgu iken
gate milisaniyeler icinde tum satirlari isaretler (bkz. DURUM 6c 'olcek uyarisi').
Ayni satir-bazli hata izolasyonu/progressive-yazim ilkeleri (eval/batch.py);
CSV yazim/resume/limit mekanigi eval/csv_runner.py'de (3 batch turu ortak)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from institution_resolver_v3.eval.csv_runner import ProgressFn, run_csv_batch
from institution_resolver_v3.gate.gate import GateDecision
from institution_resolver_v3.gate.gate import gate as _gate
from institution_resolver_v3.retrieve.resolve import resolve as _resolve

FIELDNAMES = [
    "query",
    "status",  # ok | error
    "parent_verdict",
    "parent_id",
    "parent_name",
    "parent_confidence",
    "parent_tsr",
    "parent_exact_match",
    "parent_exact_span",
    "parent_qualifier_conflict",
    "parent_bm25",
    "parent_cosine",
    "parent_reason",
    # "Oneri" (2026-08-21 karari): SAF EKLENTI - parent_id/parent_name'e
    # DOKUNMAZ. review/ambiguous + guclu exact varsa dolu ("id:Ad, id:Ad"),
    # auto_match/no_match/hata satirlarinda BOS (gate.py candidates listesini
    # zaten sadece o iki durumda dolduruyor - bkz. MAX_SUGGESTED_CANDIDATES).
    "candidates",
    "subunit_verdict",
    "subunit_id",
    "subunit_name",
    "subunit_confidence",
    "subunit_tsr",
    "subunit_exact_match",
    "subunit_exact_span",
    "subunit_qualifier_conflict",
    "subunit_bm25",
    "subunit_cosine",
    "subunit_reason",
    "unit_phrase",
    "error",
    "resolve_s",
    "gate_s",
    "result_json",
]


def _name_of(pool: list, matched_id: str | None) -> str:
    if matched_id is None:
        return ""
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else ""


def _format_candidates(pool: list, ids: list[str]) -> str:
    """Tek hucre, virgulle ayrilmis "id:Ad" ciftleri (2026-08-21 kullanici
    karari - CSV'de tek "oneri" sutunu, ayri cand1/cand2/.. kolonlari degil)."""
    by_id = {c.id: c.name for c in pool}
    return ", ".join(f"{cid}:{by_id.get(cid, '')}" for cid in ids)


def _signal_cols(prefix: str, d: GateDecision | None) -> dict[str, str]:
    """GateDecision.signals'i duz CSV kolonlarina cevirir (gosterge alanlari
    bm25/kosinus DAHIL - karara girmezler ama denetim icin CSV'de tasinirlar)."""
    s = d.signals if d is not None else {}
    cosine = s.get("cosine")
    return {
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


def process_one_gate(
    query: str,
    *,
    resolve_fn: Callable = _resolve,
    gate_fn: Callable = _gate,
    top: int = 5,
) -> dict[str, str]:
    """Tek sorgu icin resolve->gate (LLM YOK); FIELDNAMES semasinda duz kayit doner.

    gate() deterministiktir (istisna firlatmaz); buradaki try/except pratikte
    resolve()/ES baglanti hatalarini yakalar - batch.py ile ayni satir-izolasyonu
    ilkesi (bir sorgu patlarsa batch cokmez)."""
    rec = {k: "" for k in FIELDNAMES}
    rec["query"] = query
    t0 = time.time()
    try:
        res = resolve_fn(query, size=top)
        t1 = time.time()
        rec["resolve_s"] = f"{t1 - t0:.2f}"
        g = gate_fn(res)
        rec["gate_s"] = f"{time.time() - t1:.2f}"
        rec["status"] = "ok"
        rec["parent_verdict"] = g.parent.verdict
        rec["parent_id"] = g.parent.matched_id or ""
        rec["parent_name"] = _name_of(res.parents, g.parent.matched_id)
        rec.update(_signal_cols("parent", g.parent))
        rec["candidates"] = _format_candidates(res.parents, g.parent.candidates)
        if g.subunit is not None:
            rec["subunit_verdict"] = g.subunit.verdict
            rec["subunit_id"] = g.subunit.matched_id or ""
            rec["subunit_name"] = _name_of(res.subunits, g.subunit.matched_id)
            rec.update(_signal_cols("subunit", g.subunit))
        rec["unit_phrase"] = g.unit_phrase or ""
        rec["result_json"] = json.dumps(
            {
                "parent": {
                    "verdict": g.parent.verdict,
                    "matched_id": g.parent.matched_id,
                    "name": rec["parent_name"],
                    "signals": g.parent.signals,
                    "candidates": g.parent.candidates,
                },
                "subunit": (
                    None
                    if g.subunit is None
                    else {
                        "verdict": g.subunit.verdict,
                        "matched_id": g.subunit.matched_id,
                        "name": rec["subunit_name"],
                        "signals": g.subunit.signals,
                    }
                ),
                "unit_phrase": g.unit_phrase,
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001 - satir izolasyonu; batch surmeli
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return rec


def run_gate_batch(
    queries: Iterable[str],
    out_path: str | Path,
    *,
    resolve_fn: Callable = _resolve,
    gate_fn: Callable = _gate,
    top: int = 5,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """`queries`'i tek tek resolve->gate'ten gecirip `out_path`'e (CSV) yazar (LLM YOK)."""

    def _proc(query: str) -> dict[str, str]:
        return process_one_gate(query, resolve_fn=resolve_fn, gate_fn=gate_fn, top=top)

    return run_csv_batch(
        queries, out_path, FIELDNAMES, _proc, limit=limit, resume=resume, on_progress=on_progress
    )
