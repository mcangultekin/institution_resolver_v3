"""API istek/yanit semalari - retrieve/gate/judge/decide katmanlarinin dataclass
ciktilarini duz JSON'a cevirir. Bu modeller yalniz TASIMA icin; karar mantigi
burada YOK (o katmanlarda kalir, bkz. plan 'retrieve/gate/judge/decide'e
DOKUNULMAYACAK')."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Verdict = Literal["auto_match", "review", "ambiguous", "no_match"]


class QueryRequest(BaseModel):
    query: str
    top: int = 5
    # Yalniz GOSTERIM: kNN top-K'ya girmemis adaylar icin kosinusu ayrica
    # hesapla. Varsayilan KAPALI - deger hicbir karara girmiyor (500 sorguda
    # olculdu, bkz. retrieve/resolve.py `_no_cosine_fn`). Kapaliyken o
    # adaylarda `cosine: null` doner ("kNN listesine girmedi").
    with_cosine: bool = False


class JudgeQueryRequest(QueryRequest):
    model: str | None = None


# --- /match ---------------------------------------------------------------


class HypothesisOut(BaseModel):
    institution_part: str
    unit_part: str
    boundary_score: float
    matched_parent_name: str | None = None
    matched_parent_id: str | None = None


class CandidateOut(BaseModel):
    id: str
    name: str
    bm25_norm: float
    cosine: float | None = None
    token_set_ratio: float
    exact_match: bool
    passed_parent_filter: bool | None = None
    qualifier_conflict: bool
    parent_name: str | None = None  # sadece subunit adaylarinda dolu (raw'dan)


class MatchResponse(BaseModel):
    query: str
    hypotheses: list[HypothesisOut]
    parents: list[CandidateOut]
    subunits: list[CandidateOut]


# --- /gate ------------------------------------------------------------------


class GateDecisionOut(BaseModel):
    verdict: Verdict
    matched_id: str | None
    name: str | None = None
    parent_name: str | None = None  # sadece subunit karari icin dolu - hangi kuruma bagli
    confidence: float
    signals: dict[str, Any]
    # "Oneri" (2026-08-21 karari): SAF EKLENTI - matched_id/name/confidence/
    # signals'a HIC DOKUNMAZ. YALNIZ review/ambiguous + guclu exact varsa
    # dolu; YALNIZ parent kararinda (subunit'te hep bos, bkz. gate.gate.py
    # MAX_SUGGESTED_CANDIDATES docstring'i).
    candidates: list[CandidateOut] = []


class GateResponse(BaseModel):
    query: str
    parent: GateDecisionOut
    subunit: GateDecisionOut | None
    unit_phrase: str | None
    # Eslesen kaydin ES'teki TAM belgesi (ulke/alias/ror vb.) - katalog kaydi,
    # karar mantigina girmez, sadece son kullaniciya tam bilgi tasimak icin.
    parent_record: dict[str, Any] | None = None
    subunit_record: dict[str, Any] | None = None


# --- /judge -------------------------------------------------------------


class JudgeDecisionOut(BaseModel):
    verdict: Verdict
    matched_id: str | None
    name: str | None = None
    parent_name: str | None = None
    # "Oneri" (2026-08-21 karari): SAF EKLENTI. Judge review/ambiguous'ta
    # zaten TEK bir matched_id veriyor - o degeri burada AYRICA (ek olarak)
    # tasir. YALNIZ parent icin (bkz. GateDecisionOut.candidates ayni ilke).
    candidates: list[CandidateOut] = []


class JudgeResponse(BaseModel):
    query: str
    parent: JudgeDecisionOut
    subunit: JudgeDecisionOut | None
    unit_phrase: str | None
    parent_record: dict[str, Any] | None = None
    subunit_record: dict[str, Any] | None = None


# --- /decide (hibrit) ------------------------------------------------------


class DecideDecisionOut(BaseModel):
    verdict: Verdict
    matched_id: str | None
    name: str | None = None
    parent_name: str | None = None
    decided_by: Literal["gate", "judge"]
    # "Oneri" (2026-08-21 karari): SAF EKLENTI - matched_id/name/decided_by'a
    # DOKUNMAZ. review/ambiguous ise kaynagina gore dolar: decided_by=gate ->
    # gate'in kendi candidates listesi; decided_by=judge -> judge'in zaten
    # verdigi TEK matched_id (bkz. eval/decide_batch.py ayni ilke, api/routers/
    # single.py _decide_parent_candidates).
    candidates: list[CandidateOut] = []


class DecideResponse(BaseModel):
    query: str
    parent: DecideDecisionOut
    subunit: DecideDecisionOut | None
    unit_phrase: str | None
    gate: GateResponse  # denetim: LLM'e dusen satirda bile gate ne dusunuyordu
    parent_record: dict[str, Any] | None = None
    subunit_record: dict[str, Any] | None = None


# --- batch/job ---------------------------------------------------------


class JobSubmitResponse(BaseModel):
    job_id: str
    kind: Literal["gate", "judge", "decide", "inventory"]
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    total: int
    ok: int
    error: int
    skipped: int
    created_at: float
    finished_at: float | None
    error_message: str | None
    result_ready: bool


class HealthResponse(BaseModel):
    status: str
    es: bool
    ollama: bool
    embedding_model: bool
