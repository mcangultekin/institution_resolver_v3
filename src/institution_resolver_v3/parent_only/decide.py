"""Parent-only karar katmani - UC MOD.

  gate    : LLM hic cagrilmaz. Karar gate'in (auto_match/review/ambiguous/no_match).
  hybrid  : gate auto_match vermezse sorgu hakeme devredilir; nihai karar hakemin.
  llm     : her sorgu hakeme gider (gate yine hesaplanir, yalniz denetim icin).

Yonlendirme kurali cekirdek `decide/decide.py`den KASITLI olarak farkli:
orada parent auto_match OLSA BILE subunit auto degilse tum sorgu LLM'e gidiyor
(`_needs_llm`, decide.py:47-52). Burada subunit olmadigi icin tek olcut parent.
Olculen etkisi (N=120): LLM'e dusen satir %55.8 -> %38.3.

`hybrid` modda hakem gate'in auto_match'ini ezebilir - cekirdekteki davranisla
tutarli (kullanici karari 2026-08-04: "yetki asimetrisi" acik karari bu modda da
mevcut sistemle ayni birakildi, gold gelince birlikte yeniden degerlendirilecek).

Gate sonucu HANGI YOLDAN gecerse gecsin `ParentDecideResult.gate`te her zaman
saklanir - LLM'e dusen satirlarda dahi "gate ne dusunuyordu" denetimi icin
(cekirdekteki ayni ilke, bkz. eval/decide_batch.py CSV kolonlari)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from institution_resolver_v3.gate.gate import GateDecision
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.parent_only.config import max_span as _cfg_max_span
from institution_resolver_v3.parent_only.gate import gate_parent as _gate_parent
from institution_resolver_v3.parent_only.genericity import es_containment_counts as _es_counts
from institution_resolver_v3.parent_only.judge import judge_parent as _judge_parent
from institution_resolver_v3.parent_only.resolve import resolve_parent as _resolve_parent
from institution_resolver_v3.parent_only.schema import ParentOnlyResult, Verdict
from institution_resolver_v3.retrieve.resolve import ResolveResult

Mode = Literal["gate", "hybrid", "llm"]
MODES: tuple[str, ...] = ("gate", "hybrid", "llm")


@dataclass
class ParentDecideResult:
    query: str
    verdict: Verdict
    matched_id: str | None
    decided_by: str  # "gate" | "judge"
    confidence: float
    gate: GateDecision  # her zaman dolu - denetim/CSV icin
    judge: ParentOnlyResult | None  # None ise LLM hic cagrilmadi
    resolve_result: ResolveResult

    @property
    def matched_name(self) -> str:
        if self.matched_id is None:
            return ""
        c = next((c for c in self.resolve_result.parents if c.id == self.matched_id), None)
        return c.name if c else ""


def decide_parent(
    query: str,
    client: LlmClient | None = None,
    *,
    mode: Mode = "hybrid",
    size: int = 5,
    max_span: int | None = None,
    resolve_fn: Callable = _resolve_parent,
    gate_fn: Callable = _gate_parent,
    judge_fn: Callable = _judge_parent,
    count_fn: Callable = _es_counts,
    config: dict[str, Any] | None = None,
) -> ParentDecideResult:
    """Kurum (parent) kararini uretir. `mode` icin bkz. modul docstring'i.

    `client` yalniz gate DISI modlarda zorunludur; `mode="gate"` icin None
    gecilebilir (cagiran taraf Ollama kurmak zorunda kalmasin)."""
    if mode not in MODES:
        raise ValueError(f"gecersiz mode={mode!r} - beklenen: {', '.join(MODES)}")
    if mode != "gate" and client is None:
        raise ValueError(f"mode={mode!r} icin bir LLM client gerekli (mode='gate' istemiyor).")

    span = max_span if max_span is not None else _cfg_max_span(config)
    result = resolve_fn(query, size=size, max_span=span)

    # Ad ayirt-ediciligi TEK msearch'te, havuzun tamami icin (bkz. genericity.py).
    # Hem gate'in jenerik-ad korumasi hem hakem prompt'u ayni sozlugu kullanir -
    # iki kez hesaplanmaz. Hata olursa bos doner: koruma calismaz, akis surer.
    names = [c.name for c in result.parents]
    try:
        name_counts = count_fn(names) if names else {}
    except Exception:  # noqa: BLE001 - sinyal yoksa karar verilemez degil, korumasiz kalir
        name_counts = {}

    g = gate_fn(result, config=config, name_counts=name_counts)

    use_llm = mode == "llm" or (mode == "hybrid" and g.verdict != "auto_match")
    if not use_llm:
        return ParentDecideResult(
            query=result.query,
            verdict=g.verdict,
            matched_id=g.matched_id,
            decided_by="gate",
            confidence=g.confidence,
            gate=g,
            judge=None,
            resolve_result=result,
        )

    j = judge_fn(result, client, config=config, name_counts=name_counts)
    return ParentDecideResult(
        query=result.query,
        verdict=j.parent.verdict,
        matched_id=j.parent.matched_id,
        decided_by="judge",
        confidence=g.confidence,  # gate'in leksik guveni - hakem skor uretmiyor
        gate=g,
        judge=j,
        resolve_result=result,
    )
