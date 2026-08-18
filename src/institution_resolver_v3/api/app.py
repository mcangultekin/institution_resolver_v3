"""FastAPI uygulama fabrikasi - CLI'daki (`cli/main.py`) tum yeteneklerin HTTP
karsiligi. `retrieve/gate/judge/decide/eval` katmanlarina DOKUNULMADI - bu
paket sadece onlari sarmalar (bkz. plan).

Lifespan'da:
- embedding modeli bir kez isitilir (`get_model()` modul-seviyesi cache -
  aksi halde ilk istek modeli yukler, saniyeler surer),
- tek bir `OllamaClient` kurulup `app.state`'e konur (CLI'nin aksine, HER
  istekte yeniden kurulmaz - kalici httpx.Client baglanti yeniden kullanimi
  icin, bkz. judge/client.py docstring'i),
- `JobManager` (batch job'lar icin, bkz. api/jobs.py) baslatilir/kapatilir.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.api.routers import batch as batch_router
from institution_resolver_v3.api.routers import single as single_router
from institution_resolver_v3.api.schemas import HealthResponse
from institution_resolver_v3.config import load_config
from institution_resolver_v3.elastic.client import get_client
from institution_resolver_v3.embedding.encoder import get_model, is_loaded
from institution_resolver_v3.judge.client import OllamaClient

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    get_model()  # embedding modelini isit (ilk istege pahali maliyeti tasima)
    jcfg = cfg["judge"]
    app.state.ollama_client = OllamaClient(model=jcfg["model"], host=jcfg["host"])
    app.state.job_manager = JobManager()
    try:
        yield
    finally:
        app.state.ollama_client.close()
        app.state.job_manager.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Institution Resolver v3",
        description="Serbest metin kurum ifadesini kanonik parent+subunit'e cozer",
        lifespan=lifespan,
    )
    app.include_router(single_router.router)
    app.include_router(batch_router.router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def ui() -> HTMLResponse:
        """Terminal/JSON'a bogulmadan tek-kutu sorgu + CSV yukleme sayfasi
        (bkz. api/static/index.html) - Swagger/curl karmasik gelen kullanicilar icin."""
        return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        cfg = load_config()
        es_ok = False
        try:
            es_ok = bool(get_client().ping())
        except Exception:  # noqa: BLE001 - saglik kontrolu asla 500 firlatmamali
            es_ok = False
        ollama_ok = False
        try:
            r = httpx.get(f"{cfg['judge']['host']}/api/tags", timeout=3.0)
            ollama_ok = r.status_code == 200
        except Exception:  # noqa: BLE001
            ollama_ok = False
        return HealthResponse(status="ok", es=es_ok, ollama=ollama_ok, embedding_model=is_loaded())

    return app


app = create_app()


def run() -> None:
    """`inres3-serve` script girisi (bkz. pyproject.toml)."""
    import os

    import uvicorn

    uvicorn.run(
        "institution_resolver_v3.api.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
