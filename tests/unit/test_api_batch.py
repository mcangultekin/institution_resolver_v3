"""Batch (CSV upload -> job -> sonuc) API testleri - resolve/gate/judge/decide
ENJEKTE edilir (ES/Ollama'ya gidilmez). `JOBS_DIR` gercek `data/jobs`'a
yazmasin diye tmp_path'e monkeypatch'lenir."""

from __future__ import annotations

import time
from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient

from institution_resolver_v3.api import deps
from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.api.routers import batch as batch_router


def _fake_resolve(query, size=5):
    return NS(
        query=query,
        parents=[NS(id="P1", name="EGE UNIVERSITESI")],
        subunits=[NS(id="S1", name="TIP FAKULTESI")],
    )


def _fake_gate(result):
    parent_d = NS(verdict="auto_match", matched_id="P1", confidence=0.95, signals={})
    return NS(query=result.query, parent=parent_d, subunit=None, unit_phrase=None)


def _fake_judge(result, client):
    return NS(parent=NS(verdict="auto_match", matched_id="P1"), subunit=None, unit_phrase=None)


def _fake_decide(query, client, size=5):
    result = _fake_resolve(query, size=size)
    g = _fake_gate(result)
    return NS(
        query=query,
        parent=NS(verdict="auto_match", matched_id="P1", decided_by="gate"),
        subunit=None,
        unit_phrase=None,
        gate=g,
        judge=None,
        resolve_result=result,
    )


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(batch_router.router)
    app.state.ollama_client = NS()
    app.state.job_manager = JobManager()
    app.dependency_overrides[deps.get_resolve_fn] = lambda: _fake_resolve
    app.dependency_overrides[deps.get_gate_fn] = lambda: _fake_gate
    app.dependency_overrides[deps.get_judge_fn] = lambda: _fake_judge
    app.dependency_overrides[deps.get_decide_fn] = lambda: _fake_decide
    return app


def _wait_for(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/jobs/{job_id}")
        body = r.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} zamaninda bitmedi: {body}")


def test_batch_gate_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_router, "JOBS_DIR", tmp_path)
    client = TestClient(_make_app())
    csv_content = "raw_name\nege universitesi tip fakultesi\n"
    r = client.post(
        "/batch/gate",
        files={"file": ("in.csv", csv_content, "text/csv")},
        data={"query_col": "raw_name"},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    status = _wait_for(client, job_id)
    assert status["status"] == "done"
    assert status["ok"] == 1
    assert status["result_ready"] is True

    result = client.get(f"/jobs/{job_id}/result")
    assert result.status_code == 200
    assert "P1" in result.text


def test_batch_decide_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_router, "JOBS_DIR", tmp_path)
    client = TestClient(_make_app())
    csv_content = "raw_name\nege universitesi tip fakultesi\n"
    r = client.post(
        "/batch/decide",
        files={"file": ("in.csv", csv_content, "text/csv")},
        data={"query_col": "raw_name"},
    )
    job_id = r.json()["job_id"]
    status = _wait_for(client, job_id)
    assert status["status"] == "done"
    assert status["ok"] == 1


def test_batch_missing_query_col_returns_422(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_router, "JOBS_DIR", tmp_path)
    client = TestClient(_make_app())
    r = client.post(
        "/batch/gate",
        files={"file": ("in.csv", "wrong_col\nx\n", "text/csv")},
        data={"query_col": "raw_name"},
    )
    assert r.status_code == 422


def test_job_not_found_returns_404():
    client = TestClient(_make_app())
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404


def test_result_not_ready_returns_409(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_router, "JOBS_DIR", tmp_path)
    app = _make_app()
    # cok yavas bir gate_fn ile job'u "running" durumunda yakala
    def _slow_gate(result):
        time.sleep(0.3)
        return _fake_gate(result)

    app.dependency_overrides[deps.get_gate_fn] = lambda: _slow_gate
    client = TestClient(app)
    csv_content = "raw_name\nx\n"
    r = client.post(
        "/batch/gate",
        files={"file": ("in.csv", csv_content, "text/csv")},
        data={"query_col": "raw_name"},
    )
    job_id = r.json()["job_id"]
    result = client.get(f"/jobs/{job_id}/result")
    assert result.status_code == 409
