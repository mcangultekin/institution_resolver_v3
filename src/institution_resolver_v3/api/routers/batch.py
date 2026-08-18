"""Toplu (CSV) endpoint'leri - CLI'daki `gate-batch`/`batch`/`decide-batch`
komutlarinin (bkz. cli/main.py) HTTP karsiligi. CSV senkron HTTP isteginde
islenmez (438K satirlik girdiler var, bkz. plan) - dosya kaydedilip arka
plana (JobManager, bkz. api/jobs.py) atilir, `job_id` doner; durum/sonuc
GET /jobs/{id} ve GET /jobs/{id}/result'tan alinir."""

from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Callable, Iterator

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from institution_resolver_v3.api.deps import (
    get_decide_fn,
    get_gate_fn,
    get_job_manager,
    get_judge_fn,
    get_ollama_client,
    get_resolve_fn,
)
from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.api.schemas import JobStatusResponse, JobSubmitResponse
from institution_resolver_v3.eval.batch import run_batch
from institution_resolver_v3.eval.decide_batch import run_decide_batch
from institution_resolver_v3.eval.gate_batch import run_gate_batch
from institution_resolver_v3.jobs.inventory import run_inventory_batch
from institution_resolver_v3.judge.client import LlmClient

router = APIRouter(tags=["batch"])

JOBS_DIR = Path("data/jobs")


def _save_upload(job_id: str, file: UploadFile) -> Path:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    in_path = JOBS_DIR / f"{job_id}_in.csv"
    with in_path.open("wb") as f:
        f.write(file.file.read())
    return in_path


def _validate_query_col(in_path: Path, query_col: str) -> None:
    with in_path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if query_col not in header:
        raise HTTPException(
            status_code=422, detail=f"'{query_col}' kolonu CSV'de yok. Mevcut kolonlar: {header}"
        )


def _csv_queries(in_path: Path, query_col: str) -> Iterator[str]:
    with in_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            q = (row.get(query_col) or "").strip()
            if q:
                yield q


def _status_out(rec) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=rec.id,
        kind=rec.kind,
        status=rec.status,
        total=rec.total,
        ok=rec.ok,
        error=rec.error,
        skipped=rec.skipped,
        created_at=rec.created_at,
        finished_at=rec.finished_at,
        error_message=rec.error_message,
        result_ready=rec.status == "done",
    )


@router.post("/batch/gate", response_model=JobSubmitResponse)
def batch_gate(
    file: UploadFile,
    query_col: str = Form("raw_name"),
    top: int = Form(5),
    limit: int | None = Form(None),
    job_manager: JobManager = Depends(get_job_manager),
    resolve_fn: Callable = Depends(get_resolve_fn),
    gate_fn: Callable = Depends(get_gate_fn),
) -> JobSubmitResponse:
    job_id = uuid.uuid4().hex[:12]
    in_path = _save_upload(job_id, file)
    _validate_query_col(in_path, query_col)
    out_path = JOBS_DIR / f"{job_id}_out.csv"

    def _run(on_progress):
        return run_gate_batch(
            _csv_queries(in_path, query_col),
            out_path,
            resolve_fn=resolve_fn,
            gate_fn=gate_fn,
            limit=limit,
            top=top,
            on_progress=on_progress,
        )

    rec = job_manager.submit("gate", _run, out_path, job_id=job_id)
    return JobSubmitResponse(job_id=rec.id, kind="gate", status=rec.status)


@router.post("/batch/judge", response_model=JobSubmitResponse)
def batch_judge(
    file: UploadFile,
    query_col: str = Form("raw_name"),
    top: int = Form(5),
    limit: int | None = Form(None),
    job_manager: JobManager = Depends(get_job_manager),
    ollama_client: LlmClient = Depends(get_ollama_client),
    resolve_fn: Callable = Depends(get_resolve_fn),
    judge_fn: Callable = Depends(get_judge_fn),
) -> JobSubmitResponse:
    job_id = uuid.uuid4().hex[:12]
    in_path = _save_upload(job_id, file)
    _validate_query_col(in_path, query_col)
    out_path = JOBS_DIR / f"{job_id}_out.csv"

    def _run(on_progress):
        return run_batch(
            _csv_queries(in_path, query_col),
            ollama_client,
            out_path,
            resolve_fn=resolve_fn,
            judge_fn=judge_fn,
            limit=limit,
            top=top,
            on_progress=on_progress,
        )

    rec = job_manager.submit("judge", _run, out_path, job_id=job_id)
    return JobSubmitResponse(job_id=rec.id, kind="judge", status=rec.status)


@router.post("/batch/decide", response_model=JobSubmitResponse)
def batch_decide(
    file: UploadFile,
    query_col: str = Form("raw_name"),
    top: int = Form(5),
    limit: int | None = Form(None),
    job_manager: JobManager = Depends(get_job_manager),
    ollama_client: LlmClient = Depends(get_ollama_client),
    decide_fn: Callable = Depends(get_decide_fn),
) -> JobSubmitResponse:
    job_id = uuid.uuid4().hex[:12]
    in_path = _save_upload(job_id, file)
    _validate_query_col(in_path, query_col)
    out_path = JOBS_DIR / f"{job_id}_out.csv"

    def _run(on_progress):
        return run_decide_batch(
            _csv_queries(in_path, query_col),
            ollama_client,
            out_path,
            decide_fn=decide_fn,
            limit=limit,
            top=top,
            on_progress=on_progress,
        )

    rec = job_manager.submit("decide", _run, out_path, job_id=job_id)
    return JobSubmitResponse(job_id=rec.id, kind="decide", status=rec.status)


def _inventory_rows(in_path: Path, query_col: str) -> list[dict[str, str]]:
    """CLI `inventory-batch` komutuyla ayni girdi sekli (bkz. cli/main.py):
    query + normalized_name + rows. `run_inventory_batch` girdiyi iki kez
    gezdigi icin (context haritasi + sorgu akisi) liste olarak toplanir."""
    with in_path.open(newline="", encoding="utf-8") as fh:
        rows = [
            {
                "query": (r.get(query_col) or "").strip(),
                "normalized_name": r.get("normalized_name", ""),
                "rows": r.get("rows", ""),
            }
            for r in csv.DictReader(fh)
        ]
    return [r for r in rows if r["query"]]


@router.post("/batch/inventory", response_model=JobSubmitResponse)
def batch_inventory(
    file: UploadFile,
    query_col: str = Form("query"),
    top: int = Form(5),
    limit: int | None = Form(None),
    judge: bool = Form(True),
    pool_gate: str = Form("chosen"),
    job_manager: JobManager = Depends(get_job_manager),
    ollama_client: LlmClient = Depends(get_ollama_client),
    resolve_fn: Callable = Depends(get_resolve_fn),
    gate_fn: Callable = Depends(get_gate_fn),
    judge_fn: Callable = Depends(get_judge_fn),
) -> JobSubmitResponse:
    """Envanter modu (bkz. jobs/inventory.py): CLI `inventory-batch`'in HTTP
    karsiligi. Girdi CSV'si `query` (+ istege bagli `normalized_name`, `rows`)
    kolonlarini tasir - normal gate/judge/decide'dan farkli olarak subunit
    hakemi TETIKLEMEZ, yalniz gate auto_match ise subunit karari yazilir."""
    job_id = uuid.uuid4().hex[:12]
    in_path = _save_upload(job_id, file)
    _validate_query_col(in_path, query_col)
    out_path = JOBS_DIR / f"{job_id}_out.csv"
    rows = _inventory_rows(in_path, query_col)

    def _run(on_progress):
        return run_inventory_batch(
            rows,
            out_path,
            client=ollama_client if judge else None,
            judge_enabled=judge,
            resolve_fn=resolve_fn,
            gate_fn=gate_fn,
            judge_fn=judge_fn,
            top=top,
            limit=limit,
            on_progress=on_progress,
            pool_gate=None if pool_gate == "none" else pool_gate,
        )

    rec = job_manager.submit("inventory", _run, out_path, job_id=job_id)
    return JobSubmitResponse(job_id=rec.id, kind="inventory", status=rec.status)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, job_manager: JobManager = Depends(get_job_manager)) -> JobStatusResponse:
    rec = job_manager.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job bulunamadi")
    return _status_out(rec)


@router.get("/jobs", response_model=list[JobStatusResponse])
def job_list(job_manager: JobManager = Depends(get_job_manager)) -> list[JobStatusResponse]:
    return [_status_out(r) for r in job_manager.list()]


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str, job_manager: JobManager = Depends(get_job_manager)) -> FileResponse:
    rec = job_manager.get(job_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="job bulunamadi")
    if rec.status != "done":
        raise HTTPException(status_code=409, detail=f"job henuz bitmedi (durum={rec.status})")
    return FileResponse(rec.out_path, filename=f"{job_id}_sonuc.csv", media_type="text/csv")
