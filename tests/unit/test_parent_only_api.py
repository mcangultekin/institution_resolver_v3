"""parent_only/api.py endpoint testleri - resolve/gate/decide ENJEKTE edilir.

`create_app()` KULLANILMAZ: onun lifespan'i gercek embedding modelini isitip
ES/Ollama'ya baglanir (unit test kapsami disi, cekirdek test_api_single.py ile
ayni gerekce). Bunun yerine router ciplak bir FastAPI'ye mount edilir.
`/health` de bu yuzden burada test EDILMEZ.
"""

from __future__ import annotations

import csv
import io
from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient

from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.judge.judge import JudgeValidationError
from institution_resolver_v3.parent_only import api as papi


def _fake_resolve(query, *, size=5, max_span=None):
    parent = NS(
        id="P1", name="EGE ÜNİVERSİTESİ", bm25_norm=0.9, cosine=None,
        token_set_ratio=95.0, exact_match=True, exact_match_text="ege universitesi",
        best_alias="EGE UNIVERSITY", qualifier_conflict=False,
        raw={"country": "TR", "city": "İzmir"},
    )
    decomposed = NS(institution_part="ege universitesi", unit_part="", boundary_score=95.0,
                    matched_parent_name="EGE ÜNİVERSİTESİ", matched_parent_id="P1",
                    hypotheses=[])
    return NS(query=query, decomposed=decomposed, parents=[parent], subunits=[])


def _fake_gate(result, config=None, name_counts=None):
    return NS(verdict="auto_match", matched_id="P1", confidence=0.95,
              signals={"tsr": 95.0, "reason": "tek_exact"})


def _fake_decide(query, client, *, mode="hybrid", size=5, max_span=None):
    return NS(
        query=query, verdict="auto_match", matched_id="P1", matched_name="EGE ÜNİVERSİTESİ",
        decided_by="gate", confidence=0.95,
        gate=NS(verdict="auto_match", confidence=0.95,
                signals={"tsr": 95.0, "reason": "tek_exact"}),
        judge=None,
        # batch yolu `resolve_result.decomposed.institution_part`i CSV'ye yaziyor
        resolve_result=_fake_resolve(query),
    )


def _fake_decide_raises(query, client, *, mode="hybrid", size=5, max_span=None):
    raise JudgeValidationError("Hakem geçersiz bir cevap verdi.", debug="detay")


def _client(*, decide_fn=_fake_decide, job_manager=None) -> TestClient:
    app = FastAPI()
    app.include_router(papi.router)
    app.dependency_overrides[papi.get_resolve_fn] = lambda: _fake_resolve
    app.dependency_overrides[papi.get_gate_fn] = lambda: _fake_gate
    app.dependency_overrides[papi.get_count_fn] = lambda: (lambda names: {})
    app.dependency_overrides[papi.get_decide_fn] = lambda: decide_fn
    app.dependency_overrides[papi.get_ollama_client] = lambda: NS(model="fake", host="x")
    app.dependency_overrides[papi.get_job_manager] = lambda: (job_manager or JobManager())
    return TestClient(app)


def test_match_aday_listesi_doner():
    r = _client().post("/parent/match", json={"query": "ege universitesi"})
    assert r.status_code == 200
    body = r.json()
    assert body["institution_part"] == "ege universitesi"
    assert body["candidates"][0]["id"] == "P1"
    assert body["candidates"][0]["country"] == "TR"


def test_gate_karar_doner():
    r = _client().post("/parent/gate", json={"query": "ege universitesi"})
    assert r.status_code == 200
    assert r.json()["verdict"] == "auto_match"
    assert r.json()["matched_name"] == "EGE ÜNİVERSİTESİ"


def test_decide_karar_ve_gate_denetimi_doner():
    r = _client().post("/parent/decide", json={"query": "ege universitesi", "mode": "hybrid"})
    assert r.status_code == 200
    body = r.json()
    assert (body["verdict"], body["decided_by"]) == ("auto_match", "gate")
    assert body["gate_verdict"] == "auto_match" and body["gate_reason"] == "tek_exact"


def test_decide_gecersiz_mode_422():
    r = _client().post("/parent/decide", json={"query": "x", "mode": "yok"})
    assert r.status_code == 422  # pydantic Literal


def test_decide_hakem_hatasi_502():
    r = _client(decide_fn=_fake_decide_raises).post(
        "/parent/decide", json={"query": "x", "mode": "hybrid"}
    )
    assert r.status_code == 502
    assert r.json()["detail"]["debug"] == "detay"


def test_yanit_subunit_alani_icermez():
    """Sozlesme testi: parent-only yanitlarinda subunit anahtari HIC olmamali."""
    c = _client()
    for path, payload in (
        ("/parent/match", {"query": "x"}),
        ("/parent/gate", {"query": "x"}),
        ("/parent/decide", {"query": "x", "mode": "gate"}),
    ):
        assert "subunit" not in c.post(path, json=payload).text.lower()


def test_batch_gecersiz_kolon_400():
    buf = io.BytesIO(b"baska_kolon\ndeger\n")
    r = _client().post(
        "/parent/batch",
        files={"file": ("q.csv", buf, "text/csv")},
        data={"query_col": "raw_name", "mode": "gate"},
    )
    assert r.status_code == 400
    assert "raw_name" in r.json()["detail"]


def test_batch_gecersiz_mode_400():
    buf = io.BytesIO(b"raw_name\nege\n")
    r = _client().post(
        "/parent/batch", files={"file": ("q.csv", buf, "text/csv")}, data={"mode": "yok"}
    )
    assert r.status_code == 400


def test_batch_job_calisir_ve_sonuc_indirilir(tmp_path):
    jm = JobManager()
    c = _client(job_manager=jm)
    buf = io.BytesIO("raw_name\nege universitesi\ngazi universitesi\n".encode())
    r = c.post(
        "/parent/batch",
        files={"file": ("q.csv", buf, "text/csv")},
        data={"query_col": "raw_name", "mode": "gate"},
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    jm.shutdown(wait=True)  # tek isci: is bitene kadar bekle

    st = c.get(f"/parent/jobs/{job_id}").json()
    assert st["status"] == "done" and st["ok"] == 2

    res = c.get(f"/parent/jobs/{job_id}/result")
    assert res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert len(rows) == 2 and all(r["status"] == "ok" for r in rows)
    assert all(r["mode"] == "gate" and r["decided_by"] == "gate" for r in rows)


def test_bilinmeyen_job_404():
    assert _client().get("/parent/jobs/yokboyle").status_code == 404
