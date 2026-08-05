"""Parent-only aday uretimi: decompose + parent havuzu; SUBUNIT ARAMASI YOK.

`retrieve/resolve.py`'nin parent yarisini AYNEN yeniden kullanir (`_parent_union`)
- kopyalanmaz, import edilir; alias-farkindalikli tsr, `_contains_exact`in kelime
siniri korumasi, hipotez enjeksiyonu gibi kanit-yuklu mantik tek yerde kalir.

Iki fark var:
1. Subunit havuzu hic aranmaz (`ResolveResult.subunits` daima bos) - sorgu basina
   4 ES cagrisi (bm25+knn, filtreli+filtresiz) dusser.
2. Kosinus GERI-DOLDURMA yapilmaz (`_no_cosine`): kNN top-K'ya giren adaylar
   kosinusu ES skorundan almaya devam eder, ama GIRMEYENLER icin
   `_default_cosine_fn`in yaptigi ~7 mget/sorgu atlanir. Bu deger parent-only
   yolda ne gate karara katar ne prompt gosterir. Olculdu (N=150): %24 hiz,
   150/150 AYNI karar.

Doner tip bilerek mevcut `ResolveResult`: `judge/candidates.py:build_candidate_views`
ve `gate._decide_pool` bu tipi zaten biliyor, sarmalayici/donusturucu gerekmiyor.
"""

from __future__ import annotations

from typing import Any, Callable

from institution_resolver_v3.retrieve.decompose import (
    MAX_HYPOTHESES,
    BoundaryHypothesis,
    DecomposedQuery,
    _name_variants,
    decompose,
)
from institution_resolver_v3.retrieve.resolve import (
    PoolSearchFn,
    ResolveResult,
    _default_search,
    _default_search_knn,
    _parent_union,
)


def _no_cosine(text: str, hits: list[dict[str, Any]]) -> dict[str, float]:
    """Kosinus GERI-DOLDURMASINI atlar (bkz. modul docstring'i).

    Yalnizca "kNN listesinde gorunmeyen adaylarin kosinusunu AYRICA hesapla"
    adimini kapatir - kNN'de gorunenlerin kosinusu ES skorundan zaten geliyor,
    ona dokunmaz. Geri-doldurulmayanlarda `cosine` None kalir ("olculmedi");
    bu alan parent-only yolda hicbir karara girmez, yalnizca seffaflik icin
    tasinir (bm25_norm gibi)."""
    return {}


def _capped_decompose(
    query: str,
    *,
    max_span: int,
    search_many_fn: Callable[[list[str], str], list[list[dict[str, Any]]]] | None = None,
    top_k: int = 10,
) -> DecomposedQuery:
    """`decompose()` ile AYNI algoritma, tek farkla: `max_span` kelimeden uzun
    pencereler denenmez (bkz. __init__.py "SPAN SINIRI").

    Neden kopya: `decompose()` bugun bir `max_span` parametresi TASIMIYOR ve bu
    modun ugruna cekirdek dosyaya dokunulmayacak (kullanici karari 2026-08-04).
    Kopyalanan tek sey span sayimi + siralama; skorlama (`_name_variants` +
    `fuzz.ratio`) ve hipotez tipi orijinalden IMPORT edilir.

    UYARI: `max_span`, adi bu sinirdan uzun olan kurumlarin hipotezini zayiflatir
    (hicbir pencere adin tamamini kapsayamaz). Varsayilan yol `decompose()`tir;
    buraya yalnizca acikca `max_span` verilirse dusulur.
    """
    from rapidfuzz import fuzz

    from institution_resolver_v3.elastic.search import search_many
    from institution_resolver_v3.normalize.query_pipeline import expand_query_text, normalize

    surface_tokens = expand_query_text(query).split()
    if not surface_tokens:
        return DecomposedQuery(query, "", 0.0, None, None, [])

    norm_tokens = [normalize(tok).base_no_accent for tok in surface_tokens]
    n = len(surface_tokens)
    smf = search_many_fn or (lambda texts, rt: search_many(texts, rt, size=10))

    # Tek fark burasi: end, start + max_span'i asamaz.
    spans = [
        (start, end)
        for start in range(n)
        for end in range(start + 1, min(n, start + max_span) + 1)
    ]
    span_results = smf([" ".join(surface_tokens[s:e]) for s, e in spans], "parent")

    best_by_parent: dict[str, tuple[float, int, int, int, int, str | None]] = {}
    order = 0
    for (start, end), hits_all in zip(spans, span_results):
        length = end - start
        candidate_norm = " ".join(norm_tokens[start:end])
        for hit in hits_all[:top_k]:
            pid = hit.get("id")
            if pid is None:
                continue
            score = max(
                fuzz.ratio(candidate_norm, normalize(v).base_no_accent)
                for v in _name_variants(hit)
            )
            cur = best_by_parent.get(pid)
            if cur is None or score > cur[0] or (score == cur[0] and length > cur[1]):
                best_by_parent[pid] = (score, length, order, start, end, hit.get("name"))
                order += 1

    if not best_by_parent:
        return DecomposedQuery(" ".join(surface_tokens), "", 0.0, None, None, [])

    ranked = sorted(best_by_parent.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[1][2]))
    hypotheses = [
        BoundaryHypothesis(
            institution_part=" ".join(surface_tokens[start:end]),
            unit_part=" ".join(surface_tokens[:start] + surface_tokens[end:]),
            boundary_score=max(score, 0.0),
            matched_parent_name=name,
            matched_parent_id=pid,
        )
        for pid, (score, _length, _order, start, end, name) in ranked[:MAX_HYPOTHESES]
    ]
    primary = hypotheses[0]
    return DecomposedQuery(
        institution_part=primary.institution_part,
        unit_part=primary.unit_part,
        boundary_score=primary.boundary_score,
        matched_parent_name=primary.matched_parent_name,
        matched_parent_id=primary.matched_parent_id,
        hypotheses=hypotheses,
    )


def resolve_parent(
    query: str,
    *,
    size: int = 5,
    max_span: int | None = None,
    search_fn: PoolSearchFn = _default_search,
    search_knn_fn: PoolSearchFn = _default_search_knn,
    decompose_search_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
) -> ResolveResult:
    """Kurum (parent) aday havuzunu uretir; `subunits` daima BOS doner.

    `max_span=None` (varsayilan) -> cekirdek `decompose()` aynen kullanilir.
    Enjekte edilebilir `search_fn`/`decompose_search_fn`: testler gercek ES
    gerektirmesin diye (cekirdekteki `resolve()` ile ayni sozlesme).
    """
    dsf = decompose_search_fn or (lambda text, rt: search_fn(text, rt, size=10))
    # decompose'un span aramalarini tek msearch'e topla - AMA yalnizca standart
    # ES yolunda (ozel fn enjekte edildiyse span-basina o cagrilir; cekirdek
    # resolve.py'deki ayni koruma).
    if decompose_search_fn is None and search_fn is _default_search:
        from institution_resolver_v3.elastic.search import search_many

        dsm = lambda texts, rt: search_many(texts, rt, size=10)  # noqa: E731
    else:
        dsm = lambda texts, rt: [dsf(t, rt) for t in texts]  # noqa: E731

    if max_span is None:
        decomposed = decompose(query, search_fn=dsf, search_many_fn=dsm)
    else:
        decomposed = _capped_decompose(query, max_span=max_span, search_many_fn=dsm)

    parents = _parent_union(
        decomposed,
        query,
        size=size,
        search_fn=search_fn,
        search_knn_fn=search_knn_fn,
        cosine_fn=_no_cosine,
    )
    return ResolveResult(query=query, decomposed=decomposed, parents=parents, subunits=[])
