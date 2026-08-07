"""Karar katmani (F5.5): once gate (LLM'siz), parent VEYA subunit auto_match
vermezse sorgunun TAMAMI hakeme (LLM) devredilir.

Neden "tamami" (kismi degil): judge() ikisine (parent+subunit) BIRLIKTE karar
verir, tum aday havuzuna bakarak - parent'i sabit tutup yalniz subunit'i LLM'e
sormak icin ayri bir API gerekir, judge() bunu desteklemiyor. Kullanici karari
(2026-07-28): herhangi biri auto degilse tum sorgu LLM'e gider, judge'in
kararı (ikisi icin de) nihai olur - gate'in auto dedigi taraf bile ezilebilir,
ama judge zaten kalibre (bkz. DURUM 6d/6e).

Gate sonucu (sinyaller dahil) HANGI YOLDAN gecerse gecsin DecideResult.gate'te
her zaman saklanir - LLM'e dusen satirlarda dahi "gate ne dusunuyordu" denetimi
icin (bkz. eval/decide_batch.py CSV kolonlari)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from institution_resolver_v3.gate.gate import GateResult, gate as _gate
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.judge.judge import JudgeResult, judge as _judge
from institution_resolver_v3.judge.judge import judge_subunit as _judge_subunit
from institution_resolver_v3.judge.schema import Verdict
from institution_resolver_v3.retrieve.resolve import ResolveResult, resolve as _resolve


@dataclass
class DecideDecision:
    """Nihai karar (parent ya da subunit icin) + kimin verdigi."""

    verdict: Verdict
    matched_id: str | None
    decided_by: str  # "gate" | "judge"


@dataclass
class DecideResult:
    query: str
    parent: DecideDecision
    subunit: DecideDecision | None
    unit_phrase: str | None
    gate: GateResult  # her zaman dolu - denetim/CSV icin (bkz. modul docstring'i)
    judge: JudgeResult | None  # None ise gate yetti, LLM hic cagrilmadi
    resolve_result: ResolveResult


def _needs_llm(g: GateResult) -> bool:
    if g.parent.verdict != "auto_match":
        return True
    if g.subunit is not None and g.subunit.verdict != "auto_match":
        return True
    return False


def decide(
    query: str,
    client: LlmClient,
    *,
    size: int = 5,
    resolve_fn: Callable = _resolve,
    gate_fn: Callable = _gate,
    judge_fn: Callable = _judge,
    # B10: parent-sabitli subunit sorgusu. None verilirse eski davranis
    # (sorgunun tamami hakeme) - testler/geriye donuk uyum icin.
    judge_subunit_fn: Callable | None = _judge_subunit,
    config: dict[str, Any] | None = None,
) -> DecideResult:
    """resolve() -> gate(); ikisi de (parent + varsa subunit) auto_match ise
    LLM hic cagrilmaz. Degilse judge() cagrilir, nihai karar judge'den gelir."""
    result = resolve_fn(query, size=size)
    g = gate_fn(result, config=config)

    if not _needs_llm(g):
        parent = DecideDecision(g.parent.verdict, g.parent.matched_id, "gate")
        subunit = (
            None
            if g.subunit is None
            else DecideDecision(g.subunit.verdict, g.subunit.matched_id, "gate")
        )
        return DecideResult(
            query=result.query,
            parent=parent,
            subunit=subunit,
            unit_phrase=g.unit_phrase,
            gate=g,
            judge=None,
            resolve_result=result,
        )

    # B10 (2026-08-07): gate parent'a `auto_match` verdiyse parent'i SABITLE ve
    # hakeme yalnizca birimi sor. Olculen gerekce (500-sorgu baseline):
    #   - LLM'e giden 273 sorgunun 93'u tam bu durumdaydi (parent auto, subunit
    #     belirsiz) ve hakem parent kararini %90 aynen onayladi -> prompt'un
    #     parent kismi israfti.
    #   - Kosunun 33 hatasinin TAMAMI "kurum/birim uyusmazligi"ydi; enum sadece
    #     o parent'in altindaki subunit'lerle kurulunca bu hata IMKANSIZ olur.
    #   - Hakem gate'in dogru parent'ini 93 satirin 6'sinda BOZUYORDU.
    # Bedeli: gate'in parent'i yanlissa hakem artik duzeltemez. Bu, 2026-07-28'de
    # alinan "auto degilse sorgunun TAMAMI hakeme gider" kararinin bilincli
    # revizyonudur - o karar "judge() bunu desteklemiyor" gerekcesiyle alinmisti,
    # dogruluk gerekcesiyle degil; simdi ayri bir API var.
    if (
        judge_subunit_fn is not None
        and g.parent.verdict == "auto_match"
        and g.parent.matched_id is not None
        and g.subunit is not None
    ):
        j = judge_subunit_fn(result, client, parent_id=g.parent.matched_id)
    else:
        j = judge_fn(result, client)
    parent = DecideDecision(j.parent.verdict, j.parent.matched_id, "judge")
    subunit = (
        None
        if j.subunit is None
        else DecideDecision(j.subunit.verdict, j.subunit.matched_id, "judge")
    )
    return DecideResult(
        query=result.query,
        parent=parent,
        subunit=subunit,
        unit_phrase=j.unit_phrase,
        gate=g,
        judge=j,
        resolve_result=result,
    )
