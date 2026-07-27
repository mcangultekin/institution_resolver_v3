"""F5 batch: bir girdi CSV'sindeki kurum ifadelerini resolve->judge zincirinden
gecirip SONUC CSV'sine yazar (satir basina bir kayit).

Tasarim ilkeleri:
- Satir-bazli HATA IZOLASYONU: bir sorgu patlarsa (hakem/baglanti hatasi) tum
  batch cokmez; o satira status=error yazilir, sonraki satira gecilir.
- PROGRESSIVE yazim: her sonuc aninda diske flush edilir - uzun kosu ortasinda
  cokme olursa is kaybolmaz, `resume=True` ile kaldigi yerden devam eder.
- Gate/decide HENUZ YOK (bilerek - gate esikleri gold sonrasi ayarlanacak,
  decide bos). Akis su an resolve->judge; ikisi sonradan araya girecek sekilde
  process_one tek nokta olarak tutuldu.
- resolve_fn/judge_fn ENJEKTE edilebilir (test ES/Ollama'ya gitmesin diye)."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from institution_resolver_v3.judge.client import LlmError
from institution_resolver_v3.judge.judge import JudgeValidationError
from institution_resolver_v3.judge.judge import judge as _judge
from institution_resolver_v3.retrieve.resolve import resolve as _resolve

# Sonuc CSV kolonlari (insan-okur duz alanlar + tam-sadakat result_json).
FIELDNAMES = [
    "query",
    "status",  # ok | error
    "parent_verdict",  # auto_match | review | ambiguous | no_match
    "parent_id",
    "parent_name",
    "subunit_verdict",
    "subunit_id",
    "subunit_name",
    "unit_phrase",
    "error",  # status=error ise mesaj
    "resolve_s",
    "llm_s",
    "result_json",  # tam yapisal sonuc (JSON tek kolon)
]

ProgressFn = Callable[[int, str, dict[str, Any]], None]


def _name_of(pool: list, matched_id: str | None) -> str:
    if matched_id is None:
        return ""
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else ""


def process_one(
    query: str,
    client: Any,
    *,
    resolve_fn: Callable = _resolve,
    judge_fn: Callable = _judge,
    top: int = 5,
) -> dict[str, str]:
    """Tek sorgu icin resolve->judge; FIELDNAMES semasinda duz kayit doner.

    Hicbir istisna disari sizmaz - hepsi status=error olarak yakalanir (batch
    surekliligi). no_match/review/ambiguous HATA DEGILDIR: status=ok, verdict
    alaninda yazilir (sistem 'eslemedim/emin degilim' dedi, gecerli bir sonuc)."""
    rec = {k: "" for k in FIELDNAMES}
    rec["query"] = query
    t0 = time.time()
    try:
        res = resolve_fn(query, size=top)
        t1 = time.time()
        rec["resolve_s"] = f"{t1 - t0:.2f}"
        v = judge_fn(res, client)
        rec["llm_s"] = f"{time.time() - t1:.2f}"
        rec["status"] = "ok"
        rec["parent_verdict"] = v.parent.verdict
        rec["parent_id"] = v.parent.matched_id or ""
        rec["parent_name"] = _name_of(res.parents, v.parent.matched_id)
        if v.subunit is not None:
            rec["subunit_verdict"] = v.subunit.verdict
            rec["subunit_id"] = v.subunit.matched_id or ""
            rec["subunit_name"] = _name_of(res.subunits, v.subunit.matched_id)
        rec["unit_phrase"] = v.unit_phrase or ""
        rec["result_json"] = json.dumps(
            {
                "parent": {
                    "verdict": v.parent.verdict,
                    "matched_id": v.parent.matched_id,
                    "name": rec["parent_name"],
                },
                "subunit": (
                    None
                    if v.subunit is None
                    else {
                        "verdict": v.subunit.verdict,
                        "matched_id": v.subunit.matched_id,
                        "name": rec["subunit_name"],
                    }
                ),
                "unit_phrase": v.unit_phrase,
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


def run_batch(
    queries: Iterable[str],
    client: Any,
    out_path: str | Path,
    *,
    resolve_fn: Callable = _resolve,
    judge_fn: Callable = _judge,
    top: int = 5,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """`queries`'i tek tek isleyip `out_path`'e (CSV) yazar; ozet doner.

    `resume=True`: cikti dosyasi varsa icindeki 'query'ler atlanir (kaldigi
    yerden devam). `limit`: en fazla bu kadar GIRDI satiri tuketilir."""
    out_path = Path(out_path)
    done: set[str] = set()
    existing = resume and out_path.exists() and out_path.stat().st_size > 0
    if existing:
        with out_path.open(newline="", encoding="utf-8") as f:
            done = {r["query"] for r in csv.DictReader(f)}

    n_ok = n_err = n_skip = 0
    mode = "a" if existing else "w"
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not existing:
            writer.writeheader()
        for count, query in enumerate(queries, start=1):
            if limit is not None and count > limit:
                break
            if query in done:
                n_skip += 1
                continue
            rec = process_one(query, client, resolve_fn=resolve_fn, judge_fn=judge_fn, top=top)
            writer.writerow(rec)
            f.flush()  # progressive: cokme-guvenli
            if rec["status"] == "ok":
                n_ok += 1
            else:
                n_err += 1
            if on_progress is not None:
                on_progress(count, query, rec)

    return {
        "ok": n_ok,
        "error": n_err,
        "skipped": n_skip,
        "total_written": n_ok + n_err,
        "out": str(out_path),
    }
