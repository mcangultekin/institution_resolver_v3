"""In-memory batch job kaydi + tek isci calistiricisi.

Redis/Celery gibi ayri bir kuyruk altyapisi bu asamada orantisiz - CSV
batch'ler zaten uzun surebiliyor (438K satir, bkz. docs/DURUM_2026-07-27.md
6c), bu yuzden HTTP istegini o sure boyunca acik tutmak yerine arka planda
calistirilip durumu ayri sorgulanir (job_id -> GET /jobs/{id}).

Is durumu PROCESS BELLEGINDE tutulur - API yeniden baslarsa devam eden job'un
durumu kaybolur (bilinen sinir, bkz. plan). Cikti CSV'si zaten diskte ve
`resume=True` ile elle yeniden tetiklenebilir.

`max_workers=1`: batch job'lar birbiriyle VE tekli-sorgu (/match /gate /judge
/decide) trafigiyle ayni kaynaklari (ES, Ollama, embedding modeli) paylasiyor;
seri calistirma kaynak yarisini onler."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal

JobKind = Literal["gate", "judge", "decide"]
JobStatusName = Literal["pending", "running", "done", "error"]

# run_fn: on_progress callback'i alir, run_*_batch'in dondurdugu ozet dict'i doner
# (bkz. eval/csv_runner.py run_csv_batch donen sozluk: ok/error/skipped/total_written/out).
RunFn = Callable[[Callable[[int, str, dict[str, Any]], None]], dict[str, Any]]


@dataclass
class JobRecord:
    id: str
    kind: JobKind
    status: JobStatusName = "pending"
    total: int = 0
    ok: int = 0
    error: int = 0
    skipped: int = 0
    out_path: str | None = None
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inres3-job")

    def submit(
        self, kind: JobKind, run_fn: RunFn, out_path: str | Path, job_id: str | None = None
    ) -> JobRecord:
        job_id = job_id or uuid.uuid4().hex[:12]
        rec = JobRecord(id=job_id, kind=kind, out_path=str(out_path))
        with self._lock:
            self._jobs[job_id] = rec

        def _on_progress(count: int, query: str, row: dict[str, Any]) -> None:
            with self._lock:
                rec.total = count
                if row.get("status") == "ok":
                    rec.ok += 1
                else:
                    rec.error += 1

        def _run() -> None:
            with self._lock:
                rec.status = "running"
            try:
                summary = run_fn(_on_progress)
                with self._lock:
                    rec.ok = summary.get("ok", rec.ok)
                    rec.error = summary.get("error", rec.error)
                    rec.skipped = summary.get("skipped", 0)
                    rec.total = summary.get("total_written", rec.total) + rec.skipped
                    rec.status = "done"
                    rec.finished_at = time.time()
            except Exception as exc:  # noqa: BLE001 - job cokmesin, durum yakalansin
                with self._lock:
                    rec.status = "error"
                    rec.error_message = f"{type(exc).__name__}: {exc}"[:500]
                    rec.finished_at = time.time()

        self._executor.submit(_run)
        return rec

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
