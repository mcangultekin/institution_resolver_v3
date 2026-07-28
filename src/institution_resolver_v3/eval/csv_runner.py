"""CSV batch ortak iskeleti: progressive yazim + resume + limit + satir-bazli
hata izolasyonu (bkz. eval/batch.py docstring - ayni ilkeler). 3 batch turu
(llm-only, gate-only, hibrit) arasinda bu dongu TEKRARLANMASIN diye tek yerde
tutulur; her batch kendi process_one/FIELDNAMES'ini tasir, burasi sadece
CSV yazim/resume/limit mekanigidir."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable, Iterable

ProgressFn = Callable[[int, str, dict[str, Any]], None]


def run_csv_batch(
    queries: Iterable[str],
    out_path: str | Path,
    fieldnames: list[str],
    process_one: Callable[[str], dict[str, str]],
    *,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """`queries`'i tek tek `process_one`'a verip `out_path`'e (CSV) yazar; ozet doner.

    `resume=True`: cikti dosyasi varsa icindeki 'query'ler atlanir (kaldigi
    yerden devam). `limit`: en fazla bu kadar GIRDI satiri tuketilir. `process_one`
    tek argumanla (query) cagrilir - client/resolve_fn/vb. cagiran tarafin
    closure'inda kalir (bkz. batch.py/gate_batch.py/decide_batch.py run_* fonksiyonlari)."""
    out_path = Path(out_path)
    done: set[str] = set()
    existing = resume and out_path.exists() and out_path.stat().st_size > 0
    if existing:
        with out_path.open(newline="", encoding="utf-8") as f:
            done = {r["query"] for r in csv.DictReader(f)}

    n_ok = n_err = n_skip = 0
    mode = "a" if existing else "w"
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not existing:
            writer.writeheader()
        for count, query in enumerate(queries, start=1):
            if limit is not None and count > limit:
                break
            if query in done:
                n_skip += 1
                continue
            rec = process_one(query)
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
