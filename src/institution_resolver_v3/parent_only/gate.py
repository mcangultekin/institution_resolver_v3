"""Parent-only deterministik triyaj (LLM'siz) - `gate/gate.py`nin parent yarisi.

Mantik KOPYALANMADI: `gate._decide_pool` aynen import edilip cagriliyor. Bu,
exact-omurgali karar (span>=2, nitelik celiskisi, kisa-akronim korumasi) ve
parent'a ozgu katil coklu-exact kuralinin (`any_rival_blocks_auto=True`,
2026-07-30 kullanici karari) tek yerde kalmasini saglar.

Cekirdek `gate()` ile farklar:
- `_enforce_coherence` YOK: capraz-havuz tutarliligi subunit'i asagi kapamak
  icindi, ortada subunit yok.
- `unit_phrase` YOK: sorgudaki birim ifadesi bu modda bir hedef degil.
Yani parent karari cekirdektekiyle BIREBIR AYNI kaliyor - `gate()` de parent'i
tam olarak bu cagriyla uretiyor (bkz. gate.py:266). Kanit: N=150 karsilastirmada
150/150 ayni karar.
"""

from __future__ import annotations

from typing import Any

from institution_resolver_v3.gate.gate import GateDecision, _decide_pool
from institution_resolver_v3.parent_only.config import floor_tsr, generic_name_threshold
from institution_resolver_v3.retrieve.resolve import ResolveResult


def gate_parent(
    result: ResolveResult,
    *,
    config: dict[str, Any] | None = None,
    name_counts: dict[str, int] | None = None,
) -> GateDecision:
    """`resolve_parent()` sonucunu tek bir kovaya atar (LLM YOK).

    Kovalar hakemle ayni dilde: auto_match / review / ambiguous / no_match.
    `query_part` cekirdekteki gibi `decomposed.institution_part` (bos ise tum
    sorgu) - kisa-akronim korumasi bu metne bakar.

    `name_counts` (ad -> katalogda kac baska kayit adinin icinde geciyor;
    bkz. genericity.py) verilirse JENERIK-AD KORUMASI devreye girer. Fonksiyon
    SAF kalir: sayilari kendisi hesaplamaz, cagiran taraf (decide/CLI/API) tek
    msearch'le uretip gecer. Verilmezse koruma calismaz, davranis eskisi gibi.
    """
    institution_part = result.decomposed.institution_part or result.query
    decision = _decide_pool(
        result.parents,
        query_part=institution_part,
        floor_tsr=floor_tsr(config),
        any_rival_blocks_auto=True,
    )
    return _guard_generic_name(decision, result, config=config, name_counts=name_counts)


def _guard_generic_name(
    decision: GateDecision,
    result: ResolveResult,
    *,
    config: dict[str, Any] | None,
    name_counts: dict[str, int] | None,
) -> GateDecision:
    """Adi ayirt edici OLMAYAN bir adaya `auto_match` verilmesini engeller.

    YONLENDIRICIDIR, BLOKCU DEGIL: verdict `review`e cekilir ama `matched_id`
    KORUNUR - hibrit modda sorgu hakeme gider (decide: auto degilse LLM), gate-only
    modda insana bir oneriyle birlikte duser. Yanlis pozitifin bedeli fazladan bir
    hakem cagrisi, yanlis cevap DEGIL; bu yuzden esik hatasi ucuz.

    Olculen etki (460 satir, cekirdek hakemi referans): esik 3'te 16 satir
    yonlendirilir, 11 supheli auto'nun 10'u yakalanir, 6 "bosuna" cagri olur -
    o 6'nin kendisi de State Hospital / Ministerio de Salud gibi bilinen sorunlu
    kayitlar. Yakalanamayan tek vaka `Alice & Bob (France)` (akronim tuzagi,
    farkli hata sinifi - bu sinyal onu goremez).
    """
    if decision.verdict != "auto_match" or not name_counts:
        return decision
    threshold = generic_name_threshold(config)
    if threshold <= 0:
        return decision

    chosen = next((c for c in result.parents if c.id == decision.matched_id), None)
    if chosen is None:
        return decision
    count = name_counts.get(chosen.name)
    if count is None or count < threshold:
        return decision

    return GateDecision(
        verdict="review",
        matched_id=decision.matched_id,  # oneri korunur - blok degil, yonlendirme
        confidence=decision.confidence,
        signals={
            **decision.signals,
            "reason": "jenerik_ad",
            "capped_from": "auto_match",
            "name_containment": count,
        },
    )
