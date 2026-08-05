"""`inres3-parent-serve` - parent-only HTTP servisi (bkz. pyproject.toml).

Mevcut API'den (`api/app.py`) AYRI bir uygulamadir: ayri port, ayri surec, ayri
import agaci. Mevcut servise `include_router` ile baglanmadi - boylece burada bir
hata olsa bile `inres3-serve` etkilenmez (kullanici karari 2026-08-04, secenek "b").

Yeniden kullanilan cekirdek altyapi: `api/jobs.py:JobManager` (arka plan CSV
job'lari, tek isci - ES/Ollama kaynak yarisi olmasin diye) ve `judge/client.py`.
Istek/yanit semalari burada tanimli (api/schemas.py'ye dokunulmadi).

Bilinen sinir (cekirdekle ayni): job durumu PROCESS BELLEGINDE - servis yeniden
baslarsa devam eden job'un durumu kaybolur; cikti CSV'si diskte kalir ve
`resume=true` ile yeniden tetiklenebilir."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from institution_resolver_v3.api.jobs import JobManager, JobRecord
from institution_resolver_v3.config import load_config
from institution_resolver_v3.judge.client import LlmError, OllamaClient
from institution_resolver_v3.judge.judge import JudgeValidationError
from institution_resolver_v3.parent_only.batch import run_parent_batch
from institution_resolver_v3.parent_only.decide import MODES, decide_parent
from institution_resolver_v3.parent_only.gate import gate_parent
from institution_resolver_v3.parent_only.genericity import es_containment_counts
from institution_resolver_v3.parent_only.resolve import resolve_parent

_JOB_DIR = Path(tempfile.gettempdir()) / "inres3_parent_jobs"
# mode -> JobKind (api/jobs.py'nin Literal'i: gate|judge|decide) - o dosyaya
# dokunmamak icin en yakin karsiliga eslenir.
_JOB_KIND = {"gate": "gate", "llm": "judge", "hybrid": "decide"}


# --------------------------------------------------------------------- semalar
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    top: int = Field(5, ge=1, le=50)
    max_span: int | None = Field(None, ge=1, le=64)


class DecideRequest(QueryRequest):
    mode: Literal["gate", "hybrid", "llm"] = "hybrid"
    model: str | None = None


class CandidateOut(BaseModel):
    id: str
    name: str
    token_set_ratio: float
    bm25_norm: float
    exact_match: bool
    exact_match_text: str | None = None
    best_alias: str | None = None
    country: str | None = None
    city: str | None = None


class MatchResponse(BaseModel):
    query: str
    institution_part: str
    boundary_score: float
    candidates: list[CandidateOut]


class GateResponse(BaseModel):
    query: str
    verdict: str
    matched_id: str | None
    matched_name: str | None
    confidence: float
    signals: dict[str, Any]


class DecideResponse(GateResponse):
    mode: str
    decided_by: str
    gate_verdict: str
    gate_reason: str | None = None


class JobSubmitResponse(BaseModel):
    job_id: str
    mode: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    total: int
    ok: int
    error: int
    skipped: int
    out_path: str | None = None
    error_message: str | None = None


class HealthResponse(BaseModel):
    status: str
    es: bool
    ollama: bool


# ---------------------------------------------------------------- dependencies
def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_decide_fn() -> Callable:
    """Testlerde `app.dependency_overrides` ile sahte fonksiyonla degistirilir
    (cekirdek api/deps.py ile ayni ilke)."""
    return decide_parent


def get_resolve_fn() -> Callable:
    return resolve_parent


def get_gate_fn() -> Callable:
    return gate_parent


def get_count_fn() -> Callable:
    """Ad ayirt-edicilik sayaci (bkz. genericity.py). Testlerde override edilir."""
    return es_containment_counts


# ---------------------------------------------------------------------- yardim
def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        name=c.name,
        token_set_ratio=c.token_set_ratio,
        bm25_norm=c.bm25_norm,
        exact_match=c.exact_match,
        exact_match_text=c.exact_match_text,
        best_alias=c.best_alias,
        country=c.raw.get("country"),
        city=c.raw.get("city"),
    )


def _status_out(rec: JobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=rec.id,
        kind=rec.kind,
        status=rec.status,
        total=rec.total,
        ok=rec.ok,
        error=rec.error,
        skipped=rec.skipped,
        out_path=rec.out_path,
        error_message=rec.error_message,
    )


def _csv_queries(path: Path, query_col: str) -> Iterator[str]:
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            q = (row.get(query_col) or "").strip()
            if q:
                yield q


# ------------------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app: FastAPI):
    from institution_resolver_v3.embedding.encoder import get_model

    cfg = load_config()
    get_model()  # embedding modelini isit (ilk istege pahali maliyeti tasima)
    jcfg = cfg["judge"]
    app.state.ollama_client = OllamaClient(model=jcfg["model"], host=jcfg["host"])
    app.state.job_manager = JobManager()
    _JOB_DIR.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        app.state.ollama_client.close()
        app.state.job_manager.shutdown(wait=False)


# ---------------------------------------------------------------------- router
# Endpoint'ler bir APIRouter'da (cekirdek api/routers/* deseni): testler bunu
# ciplak bir FastAPI'ye mount edip `dependency_overrides` ile ES/Ollama'ya
# gitmeden kosabiliyor - `create_app()`in lifespan'i gercek modeli isitiyor.
router = APIRouter()


@router.post("/parent/match", response_model=MatchResponse)
def match(req: QueryRequest, resolve_fn: Callable = Depends(get_resolve_fn)) -> MatchResponse:
    """Aday havuzu + ham sinyaller (karar YOK)."""
    res = resolve_fn(req.query, size=req.top, max_span=req.max_span)
    return MatchResponse(
        query=res.query,
        institution_part=res.decomposed.institution_part or "",
        boundary_score=res.decomposed.boundary_score,
        candidates=[_candidate_out(c) for c in res.parents],
    )


@router.post("/parent/gate", response_model=GateResponse)
def gate_endpoint(
    req: QueryRequest,
    resolve_fn: Callable = Depends(get_resolve_fn),
    gate_fn: Callable = Depends(get_gate_fn),
    count_fn: Callable = Depends(get_count_fn),
) -> GateResponse:
    """Deterministik triyaj (LLM YOK)."""
    res = resolve_fn(req.query, size=req.top, max_span=req.max_span)
    try:
        counts = count_fn([c.name for c in res.parents]) if res.parents else {}
    except Exception:  # noqa: BLE001 - sinyal yoksa koruma kapali, akis surer
        counts = {}
    g = gate_fn(res, name_counts=counts)
    name = next((c.name for c in res.parents if c.id == g.matched_id), None)
    return GateResponse(
        query=res.query,
        verdict=g.verdict,
        matched_id=g.matched_id,
        matched_name=name,
        confidence=g.confidence,
        signals=g.signals,
    )


@router.post("/parent/decide", response_model=DecideResponse)
def decide_endpoint(
    req: DecideRequest,
    base_client: OllamaClient = Depends(get_ollama_client),
    decide_fn: Callable = Depends(get_decide_fn),
) -> DecideResponse:
    """Nihai kurum karari (mode: gate | hybrid | llm)."""
    client = None
    if req.mode != "gate":
        client = (
            base_client
            if not req.model or req.model == getattr(base_client, "model", None)
            else OllamaClient(model=req.model, host=base_client.host)
        )
    try:
        d = decide_fn(req.query, client, mode=req.mode, size=req.top, max_span=req.max_span)
    except (JudgeValidationError, LlmError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": str(exc), "debug": getattr(exc, "debug", None)},
        ) from None
    return DecideResponse(
        query=d.query,
        verdict=d.verdict,
        matched_id=d.matched_id,
        matched_name=d.matched_name or None,
        confidence=d.confidence,
        signals=d.gate.signals,
        mode=req.mode,
        decided_by=d.decided_by,
        gate_verdict=d.gate.verdict,
        gate_reason=d.gate.signals.get("reason"),
    )


@router.post("/parent/batch", response_model=JobSubmitResponse)
def batch_submit(
    file: UploadFile = File(..., description="CSV; sorgu kolonu `query_col`"),
    query_col: str = Form("raw_name"),
    mode: str = Form("hybrid"),
    top: int = Form(5),
    resume: bool = Form(False),
    workers: int = Form(1),
    base_client: OllamaClient = Depends(get_ollama_client),
    job_manager: JobManager = Depends(get_job_manager),
    decide_fn: Callable = Depends(get_decide_fn),
) -> JobSubmitResponse:
    """CSV yukle, arka planda isle. Durum: GET /parent/jobs/{job_id}."""
    import csv
    import uuid

    if mode not in MODES:
        raise HTTPException(400, f"gecersiz mode={mode!r}; beklenen: {', '.join(MODES)}")

    _JOB_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    in_path = _JOB_DIR / f"{job_id}_in.csv"
    with in_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    with in_path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f), [])
    if query_col not in header:
        in_path.unlink(missing_ok=True)
        raise HTTPException(400, f"'{query_col}' kolonu CSV'de yok. Kolonlar: {header}")

    out_path = _JOB_DIR / f"{job_id}_out.csv"
    client = None if mode == "gate" else base_client

    def _run(on_progress):
        return run_parent_batch(
            _csv_queries(in_path, query_col),
            out_path,
            client=client,
            mode=mode,  # type: ignore[arg-type]
            decide_fn=decide_fn,  # testlerde override edilebilsin (ES/Ollama'siz)
            top=top,
            resume=resume,
            on_progress=on_progress,
            max_workers=workers,
        )

    rec = job_manager.submit(_JOB_KIND[mode], _run, out_path, job_id=job_id)  # type: ignore[arg-type]
    return JobSubmitResponse(job_id=rec.id, mode=mode, status=rec.status)


@router.get("/parent/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(
    job_id: str, job_manager: JobManager = Depends(get_job_manager)
) -> JobStatusResponse:
    rec = job_manager.get(job_id)
    if rec is None:
        raise HTTPException(404, f"job bulunamadi: {job_id}")
    return _status_out(rec)


@router.get("/parent/jobs", response_model=list[JobStatusResponse])
def job_list(job_manager: JobManager = Depends(get_job_manager)) -> list[JobStatusResponse]:
    return [_status_out(r) for r in job_manager.list()]


@router.get("/parent/jobs/{job_id}/result")
def job_result(job_id: str, job_manager: JobManager = Depends(get_job_manager)) -> FileResponse:
    rec = job_manager.get(job_id)
    if rec is None:
        raise HTTPException(404, f"job bulunamadi: {job_id}")
    if rec.out_path is None or not Path(rec.out_path).exists():
        raise HTTPException(404, "sonuc dosyasi henuz yok")
    return FileResponse(rec.out_path, media_type="text/csv", filename=f"{job_id}.csv")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Institution Resolver v3 - parent-only",
        description="Serbest metin kurum ifadesini kanonik PARENT kaydina cozer (subunit aranmaz)",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        import httpx

        from institution_resolver_v3.elastic.client import get_client

        cfg = load_config()
        try:
            es_ok = bool(get_client().ping())
        except Exception:  # noqa: BLE001 - saglik kontrolu asla 500 firlatmamali
            es_ok = False
        try:
            r = httpx.get(f"{cfg['judge']['host']}/api/tags", timeout=3.0)
            ollama_ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ollama_ok = False
        return HealthResponse(status="ok", es=es_ok, ollama=ollama_ok)

    return app


app = create_app()


def run() -> None:
    """`inres3-parent-serve` script girisi. PORT env ile port secilir (varsayilan
    8001 - mevcut servisin 8000'iyle CAKISMASIN diye)."""
    import os

    import uvicorn

    uvicorn.run(
        "institution_resolver_v3.parent_only.api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8001")),
    )
