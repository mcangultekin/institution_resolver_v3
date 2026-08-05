"""Parent-only CSV batch (uc mod: gate / hybrid / llm).

CSV yazim/resume/limit/paralellik mekanigi `eval/csv_runner.py`den AYNEN gelir -
o modul zaten jenerik (fieldnames + process_one disaridan), tek satirina
dokunulmadi. Boylece `--limit`, `--resume` (baslik dogrulamali), progressive
flush, satir-bazli hata izolasyonu ve `--workers` bedava geliyor.

Gate sinyalleri HER SATIRDA yazilir (decided_by=judge olsa bile): hangi satirin
neden LLM'e dustugu sonradan denetlenebilsin diye (cekirdek decide_batch ile
ayni ilke)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from institution_resolver_v3.eval.csv_runner import ProgressFn, run_csv_batch
from institution_resolver_v3.gate.gate import GateDecision
from institution_resolver_v3.judge.client import LlmError
from institution_resolver_v3.judge.judge import JudgeValidationError
from institution_resolver_v3.parent_only.decide import (
    Mode,
    ParentDecideResult,
    decide_parent as _decide_parent,
)

FIELDNAMES = [
    "query",
    "status",  # ok | error
    "mode",  # gate | hybrid | llm
    "decided_by",  # gate | judge - LLM bu satira harcandi mi
    "verdict",
    "parent_id",
    "parent_name",
    "confidence",
    "institution_part",  # decompose'un birincil hipotezi (denetim)
    # gate sinyalleri - decided_by=judge olsa bile HER ZAMAN dolu
    "gate_verdict",
    "gate_confidence",
    "gate_tsr",
    "gate_exact_match",
    "gate_exact_span",
    "gate_qualifier_conflict",
    "gate_bm25",
    "gate_reason",
    "error",
    "elapsed_s",
    "result_json",
]


def _gate_cols(d: GateDecision | None) -> dict[str, str]:
    """GateDecision.signals -> duz CSV kolonlari.

    `cosine` kolonu YOK: karara zaten girmiyor (gosterge) ve bu yolda geri-doldurma
    kapali oldugu icin yalnizca kNN listesine giren adaylarda dolu - yari-dolu bir
    denetim kolonu tasimaya degmedi (bkz. parent_only/resolve.py)."""
    s = d.signals if d is not None else {}
    return {
        "gate_verdict": d.verdict if d is not None else "",
        "gate_confidence": f"{d.confidence:.3f}" if d is not None else "",
        "gate_tsr": str(s.get("tsr", "")) if "tsr" in s else "",
        "gate_exact_match": str(s.get("exact_match", "")) if "exact_match" in s else "",
        "gate_exact_span": str(s.get("exact_span", "")) if "exact_span" in s else "",
        "gate_qualifier_conflict": (
            str(s.get("qualifier_conflict", "")) if "qualifier_conflict" in s else ""
        ),
        "gate_bm25": str(s.get("bm25_norm", "")) if "bm25_norm" in s else "",
        "gate_reason": str(s.get("reason", "")),
    }


def process_one_parent(
    query: str,
    client: Any = None,
    *,
    mode: Mode = "hybrid",
    decide_fn: Callable = _decide_parent,
    top: int = 5,
    max_span: int | None = None,
) -> dict[str, str]:
    """Tek sorgu -> FIELDNAMES semasinda duz kayit.

    `decide_fn` ENJEKTE edilebilir (testler ES/Ollama'ya gitmesin). Istisnalar
    satir seviyesinde yakalanir - bir sorgu patlarsa batch cokmez (cekirdekteki
    ayni ilke)."""
    rec = {k: "" for k in FIELDNAMES}
    rec["query"] = query
    rec["mode"] = mode
    t0 = time.time()
    try:
        d: ParentDecideResult = decide_fn(
            query, client, mode=mode, size=top, max_span=max_span
        )
        rec["elapsed_s"] = f"{time.time() - t0:.2f}"
        rec["status"] = "ok"
        rec["decided_by"] = d.decided_by
        rec["verdict"] = d.verdict
        rec["parent_id"] = d.matched_id or ""
        rec["parent_name"] = d.matched_name
        rec["confidence"] = f"{d.confidence:.3f}"
        rec["institution_part"] = d.resolve_result.decomposed.institution_part or ""
        rec.update(_gate_cols(d.gate))
        rec["result_json"] = json.dumps(
            {
                "mode": mode,
                "decided_by": d.decided_by,
                "verdict": d.verdict,
                "matched_id": d.matched_id,
                "name": rec["parent_name"],
                "gate": {"verdict": d.gate.verdict, "signals": d.gate.signals},
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


def run_parent_batch(
    queries: Iterable[str],
    out_path: str | Path,
    *,
    client: Any = None,
    mode: Mode = "hybrid",
    decide_fn: Callable = _decide_parent,
    top: int = 5,
    max_span: int | None = None,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    """`queries`'i parent-only karar zincirinden gecirip `out_path`'e (CSV) yazar."""

    def _proc(query: str) -> dict[str, str]:
        return process_one_parent(
            query, client, mode=mode, decide_fn=decide_fn, top=top, max_span=max_span
        )

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
