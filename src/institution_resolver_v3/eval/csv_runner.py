"""CSV batch ortak iskeleti: progressive yazim + resume + limit + satir-bazli
hata izolasyonu (bkz. eval/batch.py docstring - ayni ilkeler). 3 batch turu
(llm-only, gate-only, hibrit) arasinda bu dongu TEKRARLANMASIN diye tek yerde
tutulur; her batch kendi process_one/FIELDNAMES'ini tasir, burasi sadece
CSV yazim/resume/limit mekanigidir."""

from __future__ import annotations

import csv
from collections import Counter
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
    max_workers: int = 1,
) -> dict[str, Any]:
    """`queries`'i `process_one`'a verip `out_path`'e (CSV) yazar; ozet doner.

    `resume=True`: cikti dosyasi varsa, basligi `fieldnames`'e uymuyorsa
    `ValueError` (sessiz kolon kaymasini onler); uyuyorsa icindeki her 'query'
    tekrar sayisi kadar ayni metin bu kosuda atlanir (coklu-tekrar da dogru
    korunur - bkz. `_read_done_counts`). `limit`: bu CAGRIDA fiilen YAZILAN
    (islenen) yeni satir sayisini sinirlar, zaten-yapilmis/atlanan satirlari
    saymaz - aksi halde resume+limit birlikte hic ilerlemez (onceki hata,
    bkz. 00_OZET.md T4). `process_one` tek argumanla (query) cagrilir -
    client/resolve_fn/vb. cagiran tarafin closure'inda kalir (bkz.
    batch.py/gate_batch.py/decide_batch.py run_* fonksiyonlari).

    `max_workers>1`: deney (2026-08-04, LLM hakem batch'inde ardisik cagrinin
    darbogaz olup olmadigini olcmek icin) - `process_one` bir ThreadPoolExecutor
    havuzunda es-zamanli cagrilir (LLM/ES cagrilari IO-bound; paylasilan
    httpx.Client thread-safe). CSV'ye yazim tek kilitle serilestirilir, satir
    SIRASI garanti degildir (resume 'query' metnine gore sayar, pozisyona
    degil - bu yuzden guvenli). `on_progress`'e gecen `count` gonderim sirasidir,
    tamamlanma sirasi degil."""
    out_path = Path(out_path)
    done_counts: Counter[str] = Counter()
    existing = resume and out_path.exists() and out_path.stat().st_size > 0
    if existing:
        with out_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            if list(header) != list(fieldnames):
                raise ValueError(
                    f"resume: mevcut CSV basligi uyusmuyor.\n"
                    f"  dosyada : {header}\n  beklenen: {fieldnames}"
                )
            done_counts.update(r["query"] for r in reader)

    to_process: list[tuple[int, str]] = []
    n_skip = 0
    for count, query in enumerate(queries, start=1):
        if done_counts[query] > 0:
            done_counts[query] -= 1
            n_skip += 1
            continue
        if limit is not None and len(to_process) >= limit:
            break
        to_process.append((count, query))

    n_ok = n_err = 0
    mode = "a" if existing else "w"
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not existing:
            writer.writeheader()

        def _write(count: int, query: str, rec: dict[str, str]) -> None:
            nonlocal n_ok, n_err
            writer.writerow(rec)
            f.flush()  # progressive: cokme-guvenli
            if rec["status"] == "ok":
                n_ok += 1
            else:
                n_err += 1
            if on_progress is not None:
                on_progress(count, query, rec)

        if max_workers <= 1:
            for count, query in to_process:
                _write(count, query, process_one(query))
        else:
            import threading
            from concurrent.futures import ThreadPoolExecutor, as_completed

            write_lock = threading.Lock()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_one, q): (count, q) for count, q in to_process}
                for fut in as_completed(futures):
                    count, query = futures[fut]
                    rec = fut.result()
                    with write_lock:
                        _write(count, query, rec)

    return {
        "ok": n_ok,
        "error": n_err,
        "skipped": n_skip,
        "total_written": n_ok + n_err,
        "out": str(out_path),
    }
