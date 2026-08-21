"""Tekli-sorgu endpoint'leri - CLI'daki `match`/`gate`/`judge`/`decide`
komutlarinin (bkz. cli/main.py) HTTP karsiligi. Ayni katman fonksiyonlarini
cagirir, sadece sonucu pydantic semaya doker."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException

from institution_resolver_v3.api.deps import (
    get_decide_fn,
    get_gate_fn,
    get_judge_fn,
    get_ollama_client,
    get_resolve_fn,
)
from institution_resolver_v3.api.schemas import (
    CandidateOut,
    DecideDecisionOut,
    DecideResponse,
    GateDecisionOut,
    GateResponse,
    HypothesisOut,
    JudgeDecisionOut,
    JudgeQueryRequest,
    JudgeResponse,
    MatchResponse,
    QueryRequest,
)
from institution_resolver_v3.judge.client import LlmClient, LlmError, OllamaClient
from institution_resolver_v3.judge.judge import JudgeValidationError

router = APIRouter(tags=["single"])


def _error_detail(exc: Exception) -> dict[str, str | None]:
    """Sabit/jenerik `message` + sorguya-ozel `debug` (2026-07-30, kullanici
    karari: "info butonu" - `message` her zaman gosterilir, `debug` istege
    baglidir). `LlmError`'da `debug` yok (JudgeValidationError'a ozgu), o
    zaman `None` doner - bkz. judge/judge.py `JudgeValidationError`."""
    return {"message": str(exc), "debug": getattr(exc, "debug", None)}


def _name_of(matched_id: str | None, pool) -> str | None:
    if matched_id is None:
        return None
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else None


def _record_of(matched_id: str | None, pool) -> dict | None:
    """Eslesen adayin ES'teki TAM belgesi (katalog kaydi) - `_name_of` gibi
    havuzdan bulur ama `.raw` (tum _source alanlari) doner."""
    if matched_id is None:
        return None
    c = next((c for c in pool if c.id == matched_id), None)
    return c.raw if c else None


def _parent_name_of(matched_id: str | None, pool) -> str | None:
    """Subunit'in BAGLI OLDUGU kurumun adi (kendi ES belgesindeki parent_name
    alani) - parent kararlarinda bu alan yok, otomatik None doner."""
    if matched_id is None:
        return None
    c = next((c for c in pool if c.id == matched_id), None)
    return c.raw.get("parent_name") if c else None


def _candidate_out(c) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        name=c.name,
        bm25_norm=c.bm25_norm,
        cosine=c.cosine,
        token_set_ratio=c.token_set_ratio,
        exact_match=c.exact_match,
        passed_parent_filter=c.passed_parent_filter,
        qualifier_conflict=c.qualifier_conflict,
        parent_name=c.raw.get("parent_name"),
    )


def _candidates_out(candidate_ids: list[str], pool) -> list[CandidateOut]:
    """id listesi -> tam `CandidateOut` listesi (havuzda bulunamayan id
    sessizce atlanir - gate kendi urettigi havuzdan id verdigi icin bu
    olmamasi gereken bir durum, ama halusinasyon degil)."""
    by_id = {c.id: c for c in pool}
    return [_candidate_out(by_id[cid]) for cid in candidate_ids if cid in by_id]


def _gate_response(result, verdict) -> GateResponse:
    """`matched_id`/`name`/`confidence`/`signals`/`*_record` DOKUNULMADI
    (2026-08-21 kullanici karari) - gate'in verdigi degeri her zaman tasir.
    `candidates` SAF EKLENTI (bkz. api/schemas.py GateDecisionOut)."""

    def _decision_out(d, pool) -> GateDecisionOut:
        return GateDecisionOut(
            verdict=d.verdict,
            matched_id=d.matched_id,
            name=_name_of(d.matched_id, pool),
            parent_name=_parent_name_of(d.matched_id, pool),
            confidence=d.confidence,
            signals=d.signals,
            candidates=_candidates_out(d.candidates, pool),
        )

    return GateResponse(
        query=result.query,
        parent=_decision_out(verdict.parent, result.parents),
        subunit=(
            None if verdict.subunit is None else _decision_out(verdict.subunit, result.subunits)
        ),
        unit_phrase=verdict.unit_phrase,
        parent_record=_record_of(verdict.parent.matched_id, result.parents),
        subunit_record=(
            None
            if verdict.subunit is None
            else _record_of(verdict.subunit.matched_id, result.subunits)
        ),
    )


@router.post("/match", response_model=MatchResponse)
def match(req: QueryRequest, resolve_fn: Callable = Depends(get_resolve_fn)) -> MatchResponse:
    result = resolve_fn(req.query, size=req.top, with_cosine=req.with_cosine)
    d = result.decomposed
    sources = d.hypotheses or [d]  # hipotez yoksa birincil alanlar (bkz. decompose.py)
    hyps = [
        HypothesisOut(
            institution_part=h.institution_part,
            unit_part=h.unit_part,
            boundary_score=h.boundary_score,
            matched_parent_name=h.matched_parent_name,
            matched_parent_id=h.matched_parent_id,
        )
        for h in sources
    ]
    return MatchResponse(
        query=result.query,
        hypotheses=hyps,
        parents=[_candidate_out(c) for c in result.parents],
        subunits=[_candidate_out(c) for c in result.subunits],
    )


@router.post("/gate", response_model=GateResponse)
def gate_endpoint(
    req: QueryRequest,
    resolve_fn: Callable = Depends(get_resolve_fn),
    gate_fn: Callable = Depends(get_gate_fn),
) -> GateResponse:
    result = resolve_fn(req.query, size=req.top, with_cosine=req.with_cosine)
    verdict = gate_fn(result)
    return _gate_response(result, verdict)


_SUGGESTIBLE = ("review", "ambiguous")


def _judge_parent_candidates(verdict, pool) -> list[CandidateOut]:
    """Judge review/ambiguous'ta zaten TEK bir matched_id veriyor - "oneri"
    o degeri AYRICA (ek olarak) tasir, karar/matched_id alanina DOKUNMAZ
    (2026-08-21 karari). YALNIZ parent icin - subunit'e hic uygulanmiyor."""
    if verdict.verdict not in _SUGGESTIBLE or verdict.matched_id is None:
        return []
    return _candidates_out([verdict.matched_id], pool)


def _decide_parent_candidates(d, pool) -> list[CandidateOut]:
    """`/decide`'in final parent karari review/ambiguous ise "oneri"yi
    kaynagina gore doldurur (2026-08-21 karari, eval/decide_batch.py
    `_decide_candidates_cell` ile AYNI ilke): `decided_by=gate` -> gate'in
    kendi candidates listesi (bkz. d.gate.parent - pratikte bu dal decide()'in
    kendi mantigi geregi HEP auto_match'te calisir, o yuzden bos gelir);
    `decided_by=judge` -> judge'in zaten verdigi TEK matched_id."""
    if d.parent.verdict not in _SUGGESTIBLE:
        return []
    ids = (
        d.gate.parent.candidates
        if d.parent.decided_by == "gate"
        else ([d.parent.matched_id] if d.parent.matched_id else [])
    )
    return _candidates_out(ids, pool)


def _judge_client(req: JudgeQueryRequest, base_client: LlmClient) -> LlmClient:
    if req.model and isinstance(base_client, OllamaClient) and req.model != base_client.model:
        return OllamaClient(model=req.model, host=base_client.host)
    return base_client


@router.post("/judge", response_model=JudgeResponse)
def judge_endpoint(
    req: JudgeQueryRequest,
    resolve_fn: Callable = Depends(get_resolve_fn),
    judge_fn: Callable = Depends(get_judge_fn),
    ollama_client: LlmClient = Depends(get_ollama_client),
) -> JudgeResponse:
    result = resolve_fn(req.query, size=req.top, with_cosine=req.with_cosine)
    client = _judge_client(req, ollama_client)
    try:
        verdict = judge_fn(result, client)
    except (JudgeValidationError, LlmError) as exc:
        raise HTTPException(status_code=502, detail=_error_detail(exc)) from None
    return JudgeResponse(
        query=result.query,
        parent=JudgeDecisionOut(
            verdict=verdict.parent.verdict,
            matched_id=verdict.parent.matched_id,
            name=_name_of(verdict.parent.matched_id, result.parents),
            candidates=_judge_parent_candidates(verdict.parent, result.parents),
        ),
        subunit=(
            None
            if verdict.subunit is None
            else JudgeDecisionOut(
                verdict=verdict.subunit.verdict,
                matched_id=verdict.subunit.matched_id,
                name=_name_of(verdict.subunit.matched_id, result.subunits),
                parent_name=_parent_name_of(verdict.subunit.matched_id, result.subunits),
            )
        ),
        unit_phrase=verdict.unit_phrase,
        parent_record=_record_of(verdict.parent.matched_id, result.parents),
        subunit_record=(
            None
            if verdict.subunit is None
            else _record_of(verdict.subunit.matched_id, result.subunits)
        ),
    )


@router.post("/decide", response_model=DecideResponse)
def decide_endpoint(
    req: JudgeQueryRequest,
    decide_fn: Callable = Depends(get_decide_fn),
    ollama_client: LlmClient = Depends(get_ollama_client),
) -> DecideResponse:
    client = _judge_client(req, ollama_client)
    try:
        d = decide_fn(req.query, client, size=req.top, with_cosine=req.with_cosine)
    except (JudgeValidationError, LlmError) as exc:
        raise HTTPException(status_code=502, detail=_error_detail(exc)) from None
    return DecideResponse(
        query=d.query,
        parent=DecideDecisionOut(
            verdict=d.parent.verdict,
            matched_id=d.parent.matched_id,
            name=_name_of(d.parent.matched_id, d.resolve_result.parents),
            decided_by=d.parent.decided_by,
            candidates=_decide_parent_candidates(d, d.resolve_result.parents),
        ),
        subunit=(
            None
            if d.subunit is None
            else DecideDecisionOut(
                verdict=d.subunit.verdict,
                matched_id=d.subunit.matched_id,
                name=_name_of(d.subunit.matched_id, d.resolve_result.subunits),
                parent_name=_parent_name_of(d.subunit.matched_id, d.resolve_result.subunits),
                decided_by=d.subunit.decided_by,
            )
        ),
        unit_phrase=d.unit_phrase,
        gate=_gate_response(d.resolve_result, d.gate),
        parent_record=_record_of(d.parent.matched_id, d.resolve_result.parents),
        subunit_record=(
            None
            if d.subunit is None
            else _record_of(d.subunit.matched_id, d.resolve_result.subunits)
        ),
    )
