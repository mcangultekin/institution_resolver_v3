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
    # B4 (2026-08-06): kNN top-K'ya girmemis adaylar icin kosinusu AYRICA
    # hesapla. Varsayilan KAPALI - deger hicbir karara girmiyor, yalniz
    # gosterim/hata ayiklama icin (gerekce: retrieve/resolve.py _no_cosine_fn).
    # Kapaliyken o adaylarda `cosine: null` doner ("kNN listesine girmedi");
    # kNN'e girenler degerini almaya devam eder.
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
    kind: Literal["gate", "judge", "decide"]
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
