"""Gate - Asama 1: LLM'siz, deterministik triyaj (guven-tabanli yonlendirme).

Girdi bir `resolve()` sonucudur; cikti TEK bir cevap (parent + varsa subunit) ve
her biri icin hakemle AYNI DILDE bir kova etiketidir:
`auto_match / review / ambiguous / no_match` (bkz. judge/schema.py Verdict).

KARAR OMURGASI = `exact_match` (aday adi/alias'i sorguda ARDISIK geciyor mu).
Genis ornek testi (v2 isimler_tekrarsız, N=200) bunu dogruladi:
- exact ile gelen auto'lar temiz (%58); bunlarin ~1/4'u alias-exact -> capraz-dil
  (ör. "Hacettepe University" -> HACETTEPE ÜNİVERSİTESİ) zaten burada cozulur.
- bm25_norm ve kosinus SIRALAMAYA/KARARA GIRMEZ. bm25_norm sorgu-ici goreli
  (1. aday daima ~1.0, cop de dahil -> tabani sisirir); kosinus anizotropik
  (DURUM 6b: havuz-ici gercek eslesmeyi 1/8 kez 1. siraya koydu). Ikisi de yalniz
  `signals`ta seffaflik icin tasinir.

Neyin AUTO oldugu (tek_exact): en iyi exact aday + span>=2 (tek generic token'la
auto YOK - gozlemlenen yanlis-auto'lar span=1'di: "Acıbadem Hastanesi"->sube) +
qualifier celiskisi yok + kisa-akronim degil + KARSISINDA esit-uzun ikinci exact
YOK. Iki esit-uzun exact -> `ambiguous` (gercek ikiz). Hic exact yoksa: en iyi
tsr taban altiysa `no_match`, degilse `review`.

DIKKAT (kapsam - denenip BIRAKILDI, 2026-07-28): exact ISKALAYAN kurtarilabilir
vakalar (yazim hatasi/kelime sirasi, ör. "Bozok Ünivesitesi") su an `review`e
duser. Bunlari kurtarmak icin marj-kapili tsr-auto (#6, ayirt-edici-token kapsama
kilidiyle) denendi ve CIKARILDI: guvenligi decompose.institution_part'a dayaniyordu,
ama decompose dagınık string'lerde onu bozuyor ("Calcutta ... Sciences" ->
kurum='Sciences'; "Acıbadem ... İstanbul" -> sehir birim'e duser) -> olculen iki
yanlisi (locator dusmesi / sehir celiskisi) bloklayamadi. Asil darbogaz UPSTREAM
(decompose kalitesi + sehir gazetteer); orasi duzelmeden tekrar denenmemeli.

Esikler placeholder (config.gate.garbage_lexical_floor); gercek etiketli set (gold)
HENUZ YOK, kova sinirlari bir maliyet/triyaj optimizasyonudur, gold gelince BIR KEZ
kalibre edilir (Ayrim 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from institution_resolver_v3.config import load_config
from institution_resolver_v3.judge.schema import Verdict
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate

# --- Guven/karar sabitleri (placeholder, gold sonrasi kalibre - modul docstring'i) ---
EXACT_BONUS = 0.10       # exact (span>=2) adayin guven skoruna kucuk katki
CONFLICT_PENALTY = 0.30  # qualifier celiskisi -> guven cezasi
MIN_EXACT_SPAN = 2       # auto icin exact eslesmenin en az token sayisi (generic koruma)
_ACRONYM_MAX_LEN = 5     # tek token, <=5 harf -> kisa akronim (METU/ITU): auto YOK


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _exact_span(c: ScoredCandidate) -> int:
    """exact eslesen ad/alias'in token sayisi (exact degilse 0). Uzun span =
    daha ayirt edici kanit; tek-token generic exact (span 1) auto'ya yetmez."""
    if not c.exact_match:
        return 0
    return len((c.exact_match_text or "").split())


def _is_strong_exact(c: ScoredCandidate) -> bool:
    """Auto'ya aday olacak kadar guclu exact: span>=MIN_EXACT_SPAN, celiski yok."""
    return c.exact_match and not c.qualifier_conflict and _exact_span(c) >= MIN_EXACT_SPAN


def score_candidate(c: ScoredCandidate) -> float:
    """Adayin [0,1] GUVEN skoru - yalniz `confidence` alani + gosterim icin.

    Leksik (tsr) tabanli; bm25/kosinus GIRMEZ (bkz. modul docstring'i). Bu skor
    SIRALAMA/KARAR icin kullanilmaz (karar exact-omurgali); adaylar arasi secim
    (span, tsr) ikilisiyle yapilir - bu yalniz insana gosterilen bir buyukluk."""
    base = c.token_set_ratio / 100.0
    if _is_strong_exact(c):
        base += EXACT_BONUS
    if c.qualifier_conflict:
        base -= CONFLICT_PENALTY
    return _clamp01(base)


def _is_short_acronym(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and " " not in t and len(t) <= _ACRONYM_MAX_LEN


@dataclass
class GateDecision:
    """Tek havuz (parent ya da subunit) icin gate karari."""

    verdict: Verdict
    matched_id: str | None
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    query: str
    parent: GateDecision
    subunit: GateDecision | None  # None = sorguda birim ifadesi YOK (hakemdeki mantik)
    unit_phrase: str | None = None


def _signals_of(c: ScoredCandidate | None, *, reason: str) -> dict[str, Any]:
    """Karari besleyen ham sinyaller (bm25/kosinus SADECE gosterim - karara girmez)."""
    if c is None:
        return {"reason": reason}
    return {
        "tsr": c.token_set_ratio,
        "exact_match": c.exact_match,
        "exact_span": _exact_span(c),
        "qualifier_conflict": c.qualifier_conflict,
        "bm25_norm": round(c.bm25_norm, 3),  # gosterim
        "cosine": (round(c.cosine, 3) if c.cosine is not None else None),  # gosterim
        "reason": reason,
    }


def _decide_pool(
    candidates: list[ScoredCandidate],
    *,
    query_part: str,
    floor_tsr: float,
    prefer_parent_id: str | None = None,
) -> GateDecision:
    """Bir havuzu (parent/subunit) exact-omurgali triyajdan gecirip TEK kovaya atar.

    prefer_parent_id (yalniz subunit): parent karari verildikten sonra, secilen
    parent'in ALTINDAKI subunit adaylari tercih edilir - ayni adli subunit farkli
    parent'larda oldugunda (ör. iki universitede "GERİATRİ BİLİM DALI") dogru
    olani secilir; o parent altinda hic exact yoksa tum exact'lere geri donulur.
    """
    if not candidates:
        return GateDecision("no_match", None, 0.0, {"reason": "bos_havuz"})

    best_tsr = max(c.token_set_ratio for c in candidates)
    display = max(candidates, key=lambda c: c.token_set_ratio)  # en iyi tsr'li - gosterim
    exact = [c for c in candidates if _is_strong_exact(c)]

    if not exact:
        if best_tsr < floor_tsr * 100.0:
            return GateDecision("no_match", None, _clamp01(best_tsr / 100.0),
                                _signals_of(display, reason="taban_alti"))
        # sinyal var ama exact degil (typo/kelime-sirasi/capraz-dil-alias-yok) ->
        # review (bkz. modul docstring'i: tsr-auto denenip birakildi, upstream isi).
        return GateDecision("review", None, _clamp01(best_tsr / 100.0),
                            _signals_of(display, reason="exact_yok"))

    # subunit: secilen parent'in altindakileri tercih et (varsa)
    if prefer_parent_id is not None:
        under = [c for c in exact if c.raw.get("parent_id") == prefer_parent_id]
        if under:
            exact = under

    best = max(exact, key=lambda c: (_exact_span(c), c.token_set_ratio))
    conf = score_candidate(best)

    if _is_short_acronym(query_part):
        return GateDecision("review", best.id, conf, _signals_of(best, reason="akronim"))

    rivals = [c for c in exact if c.id != best.id and _exact_span(c) >= _exact_span(best)]
    if rivals:
        return GateDecision("ambiguous", best.id, conf, _signals_of(best, reason="coklu_exact"))

    return GateDecision("auto_match", best.id, conf, _signals_of(best, reason="tek_exact"))


def _enforce_coherence(
    parent: GateDecision, subunit: GateDecision, subunit_pool: list[ScoredCandidate]
) -> GateDecision:
    """Capraz-havuz tutarlilik: subunit, parent'tan daha EMIN olamaz.

    subunit `auto_match` YALNIZCA parent da `auto_match` VE secilen subunit gercekten
    o parent'in ALTINDAysa gecerli kalir. Aksi halde "kurumu kesin bilmiyorum ama
    alt-birimden eminim" tutarsizligi olusur - Dalga 0'da (50-sorgu DENEY seti) CANLI
    gozlemlendi: #29 parent=review (matched_id=None) iken sub=auto hicbir parent'a
    bagli degildi; #1 parent=ambiguous iken sub=auto secilen ikizi asiri-iddia
    ediyordu. Bu durumda verdict `review`e cekilir; matched_id ONERI olarak KORUNUR
    (atilmaz - decide/ ya da hakem degerlendirsin), gerekce signals'a yazilir.

    Diger subunit verdict'leri (review/ambiguous/no_match/none) zaten auto'dan zayif,
    dokunulmaz. Not: bu YALNIZ kapama (down-cap); ters yon - guclu subunit'in belirsiz
    parent'i NETLESTIRMESI (promosyon) - bilerek DISARIDA, o decide/ katmaninin isi."""
    if subunit.verdict != "auto_match":
        return subunit
    under_parent = any(
        c.id == subunit.matched_id and c.raw.get("parent_id") == parent.matched_id
        for c in subunit_pool
    )
    if parent.verdict == "auto_match" and under_parent:
        return subunit
    return GateDecision(
        verdict="review",
        matched_id=subunit.matched_id,  # ONERI olarak korunur - atilmaz
        confidence=subunit.confidence,
        signals={
            **subunit.signals,
            "reason": "parent_kesin_degil",
            "capped_from": "auto_match",
            "parent_verdict": parent.verdict,
        },
    )


def gate(result: ResolveResult, *, config: dict[str, Any] | None = None) -> GateResult:
    """resolve() sonucunu deterministik triyajdan gecirir (LLM YOK).

    Esik config.gate.garbage_lexical_floor'dan (placeholder - gold sonrasi kalibre).
    subunit: sorguda birim ifadesi (decompose.unit_part) YOKSA None; varsa havuz bos
    olsa bile no_match (istendi ama bulunamadi - hakemdeki ayrim). Subunit karari,
    secilen parent'a baglanir (parent auto/review/ambiguous ise matched_id'sine) ve
    SON adimda tutarlilik kapisindan gecer (_enforce_coherence): subunit parent'tan
    daha emin olamaz - parent auto degilse subunit auto -> review'e cekilir.
    """
    gc = (config or load_config()).get("gate", {})
    floor_tsr = float(gc.get("garbage_lexical_floor", 0.55))

    institution_part = result.decomposed.institution_part or result.query
    parent = _decide_pool(result.parents, query_part=institution_part, floor_tsr=floor_tsr)

    unit_phrase = (result.decomposed.unit_part or "").strip() or None
    if unit_phrase is None:
        subunit: GateDecision | None = None
    else:
        subunit = _decide_pool(
            result.subunits, query_part=unit_phrase, floor_tsr=floor_tsr,
            prefer_parent_id=parent.matched_id,
        )
        subunit = _enforce_coherence(parent, subunit, result.subunits)

    return GateResult(query=result.query, parent=parent, subunit=subunit, unit_phrase=unit_phrase)
