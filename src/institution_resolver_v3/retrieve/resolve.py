"""Parent-first cascade + sinyaller (SIRADAKI ISLER 1, docs/DURUM.md).

Akis (2026-07-23 revizyonu: coklu-hipotez, recall-yonelimli):
1. `decompose()` sorgu icin BIRDEN FAZLA kurum-siniri hipotezi dondurur
   (bkz. decompose.py "KARAR DEGIL HIPOTEZ"). Secim burada da YAPILMAZ.
2. HER hipotezin kurum kismiyla PARENT havuzu ayri aranir; havuzlar
   recall-guvenli birlestirilir (birincil hipotezin sonuclari once, diger
   hipotezlerden gelen YENI adaylar sona eklenir). Boylece decompose'un
   birincil hipotezi yanlissa dogru parent havuzdan dusmez.
3. SUBUNIT, makul parent'larin TAMAMIYLA (`terms` filtresi: en guclu parent
   adayi + her hipotezin isaret ettigi parent) FILTRELI aranir. Ayrica
   (hepsi yanlis cikmis olabilir ihtimaline karsi) FILTRESIZ de aranir -
   ikisi birlestirilir (filtreli once, filtresizde olup filtrelide
   olmayanlar sona). Bu, "recall-guvenli" cascade: parent tahminleri yanlissa
   bile dogru subunit tamamen kaybolmaz, sadece sirada geriye duser.
   ESIK YOK - docs/DURUM.md calisma tarzi geregi esik tahmini icin etiketli
   set gerekir.
4. Her aday icin HAM sinyaller hesaplanir (RRF'nin ezdigi tek-boyutlu skor
   yerine, gate/LLM katmaninin ayri ayri degerlendirebilecegi kanit):
   - bm25_norm: ham BM25 skoru, o sorgunun kendi listesindeki en yuksek
     skora bolunerek [0,1]'e normalize edilir (listeler-arasi sabit bir
     esik degil, HER sorgu kendi icinde normalize edilir).
   - cosine: ES'in kNN skorundan (`similarity=cosine` mapping, bkz.
     elastic/mappings.py) geri cikarilan gercek kosinus benzerligi
     (`2*es_score - 1`); aday kNN havuzunda hic gorunmediyse `None`
     ("olculmedi" - "dusuk benzerlik olculdu" ile KARISTIRILMAMALI, 0.0
     DEGIL: bir tuketici bunu 0.0 sanip adayi haksiz yere cezalandirabilir,
     ozellikle F4'teki LLM hakem JSON'da bu alani kanit olarak okuyacak).
   - token_set_ratio: rapidfuzz, sorgu ile aday adi arasinda (aksan/case
     normalize edilmis).
   - qualifier_conflict: `normalize.qualifiers.qualifiers_conflict` (var
     olan, zaten test edilmis fonksiyon - burada tekrar yazilmadi).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from rapidfuzz import fuzz

from institution_resolver_v3.normalize.qualifiers import extract_qualifiers, qualifiers_conflict
from institution_resolver_v3.normalize.query_pipeline import normalize
from institution_resolver_v3.retrieve.decompose import DecomposedQuery, decompose

PoolSearchFn = Callable[..., list[dict[str, Any]]]


@dataclass
class ScoredCandidate:
    id: str
    record_type: str
    name: str
    raw: dict[str, Any]
    bm25_norm: float = 0.0
    cosine: float | None = None  # None = kNN top-K'ya girmedi (olculmedi, "dusuk benzerlik" DEGIL)
    token_set_ratio: float = 0.0
    qualifier_conflict: bool = False
    passed_parent_filter: bool | None = None  # sadece subunit icin anlamli


@dataclass
class ResolveResult:
    query: str
    decomposed: DecomposedQuery
    parents: list[ScoredCandidate] = field(default_factory=list)
    subunits: list[ScoredCandidate] = field(default_factory=list)


def _default_search(text: str, record_type: str, *, extra_filters=None, size: int = 50) -> list[dict[str, Any]]:
    from institution_resolver_v3.elastic.search import search

    return search(text, record_type, extra_filters=extra_filters, size=size)


def _default_search_knn(text: str, record_type: str, *, extra_filters=None, size: int = 50) -> list[dict[str, Any]]:
    from institution_resolver_v3.elastic.search import search_knn

    return search_knn(text, record_type, extra_filters=extra_filters, size=size)


def _rrf_merge(rank_lists: list[list[dict[str, Any]]], *, size: int) -> list[dict[str, Any]]:
    from institution_resolver_v3.elastic.search import rrf_merge

    return rrf_merge(rank_lists, size=size)


def _pool_with_raw_scores(
    text: str,
    record_type: str,
    *,
    extra_filters: list[dict[str, Any]] | None,
    size: int,
    search_fn: PoolSearchFn,
    search_knn_fn: PoolSearchFn,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float], float]:
    """BM25+kNN'i AYRI cagirir (ham skorlar korunur), RRF sadece havuzlama/siralama icin."""
    bm25_hits = search_fn(text, record_type, extra_filters=extra_filters, size=size)
    knn_hits = search_knn_fn(text, record_type, extra_filters=extra_filters, size=size)
    merged = _rrf_merge([bm25_hits, knn_hits], size=size)
    bm25_by_id = {h["id"]: h["score"] for h in bm25_hits}
    knn_by_id = {h["id"]: h["score"] for h in knn_hits}
    max_bm25 = max(bm25_by_id.values(), default=0.0) or 1.0
    return merged, bm25_by_id, knn_by_id, max_bm25


def _merge_filtered_first(
    filtered: list[dict[str, Any]], unfiltered: list[dict[str, Any]], *, size: int
) -> list[dict[str, Any]]:
    """Recall-guvenli birlesim: filtreli sonuclar once (parent_id kanitlanmis), filtresizde
    olup filtrelide OLMAYANLAR sona eklenir (parent tahmini yanlissa dogru aday kaybolmasin)."""
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for h in filtered:
        if h["id"] not in seen:
            seen.add(h["id"])
            ordered.append({**h, "passed_parent_filter": True})
    for h in unfiltered:
        if h["id"] not in seen:
            seen.add(h["id"])
            ordered.append({**h, "passed_parent_filter": False})
    return ordered[:size]


def _attach_signals(
    hits: list[dict[str, Any]],
    *,
    bm25_by_id: dict[str, float],
    knn_by_id: dict[str, float],
    max_bm25: float,
    query_text: str,
) -> list[ScoredCandidate]:
    query_norm = normalize(query_text).base_no_accent
    query_quals = extract_qualifiers(query_text)
    out: list[ScoredCandidate] = []
    for h in hits:
        name = h.get("name", "") or ""
        name_norm = normalize(name).base_no_accent
        bm25_raw = bm25_by_id.get(h["id"])
        bm25_norm = (bm25_raw / max_bm25) if bm25_raw is not None else 0.0
        knn_raw = knn_by_id.get(h["id"])
        cosine = (2.0 * knn_raw - 1.0) if knn_raw is not None else None
        tsr = fuzz.token_set_ratio(query_norm, name_norm)
        conflict = qualifiers_conflict(query_quals, extract_qualifiers(name))
        out.append(
            ScoredCandidate(
                id=h["id"],
                record_type=h.get("record_type", ""),
                name=name,
                raw=h,
                bm25_norm=bm25_norm,
                cosine=cosine,
                token_set_ratio=tsr,
                qualifier_conflict=conflict,
                passed_parent_filter=h.get("passed_parent_filter"),
            )
        )
    return out


# Cascade `terms` filtresine en fazla kac farkli parent_id girer (en guclu
# parent adayi + hipotezlerin isaret ettikleri; recall icin genis, ama sinirsiz
# degil - filtre anlamini yitirmesin). 4 -> 6: MAX_HYPOTHESES 5'e cikinca
# (bkz. decompose.py) tum hipotez parent'lari + en guclu aday sigsin.
MAX_CASCADE_PARENTS = 6

# Birincil-olmayan her hipotezin parent havuzuna katabilecegi YENI aday sayisi
# (birincil hipotez `size` kadar getirir; alternatifler havuzu sisirmeden
# sadece kendi en guclu adaylarini ekler).
ALT_HYPOTHESIS_CONTRIB = 3


def _parent_union(
    decomposed,
    query: str,
    *,
    size: int,
    search_fn: PoolSearchFn,
    search_knn_fn: PoolSearchFn,
) -> list[ScoredCandidate]:
    """Her hipotezin kurum kismiyla ayri parent aramasi; recall-guvenli birlesim.

    Birincil hipotezin sonuclari once ve `size` kadar; sonraki hipotezler
    yalnizca havuzda OLMAYAN ilk ALT_HYPOTHESIS_CONTRIB adayini ekler.
    bm25_norm her aramanin KENDI ICINDE normalize edilir (farkli sorgu
    metinlerinin ham BM25'leri karsilastirilamaz). token_set_ratio ve
    qualifier_conflict ise TAM ORIJINAL SORGUYA gore hesaplanir - hipotezin
    kendi parcasina gore hesaplansaydi tek kelimelik jenerik bir parca
    ("üniversitesi") uzerinden alakasiz adaylar tsr=100 alirdi (canli
    dogrulandi: Biruni/Selçuk/Boğaziçi); `token_set_ratio` sorgudaki fazla
    kelimeye zaten toleransli, dogru parent tam sorguya karsi da 100 alir.
    """
    parts_seen: set[str] = set()
    ids_seen: set[str] = set()
    union: list[ScoredCandidate] = []
    for rank, hyp in enumerate(decomposed.hypotheses or [decomposed]):
        part = hyp.institution_part
        if not part or part in parts_seen:
            continue
        parts_seen.add(part)
        merged, bm25, knn, max_bm25 = _pool_with_raw_scores(
            part, "parent", extra_filters=None, size=size,
            search_fn=search_fn, search_knn_fn=search_knn_fn,
        )
        cands = _attach_signals(
            merged, bm25_by_id=bm25, knn_by_id=knn, max_bm25=max_bm25, query_text=query
        )
        budget = size if rank == 0 else ALT_HYPOTHESIS_CONTRIB
        added = 0
        for c in cands:
            if added >= budget:
                break
            if c.id in ids_seen:
                continue
            ids_seen.add(c.id)
            union.append(c)
            added += 1

    # Hipotezin isaret ettigi parent, havuz aramalarinin top-K'sina girmemis
    # olabilir (canli ornek: "JAMSTEC," aramasinda dogru kayit rank 7'de, kisa
    # fuzzy-junk adlar ustte) - hakemin degerlendirebilmesi icin asgari
    # sinyallerle enjekte edilir (bm25_norm=0.0: listeye girmedi; cosine=None:
    # olculmedi).
    query_norm = normalize(query).base_no_accent
    query_quals = extract_qualifiers(query)
    for hyp in decomposed.hypotheses or []:
        pid = hyp.matched_parent_id
        name = hyp.matched_parent_name or ""
        if pid is None or pid in ids_seen:
            continue
        ids_seen.add(pid)
        union.append(
            ScoredCandidate(
                id=pid,
                record_type="parent",
                name=name,
                raw={"id": pid, "record_type": "parent", "name": name, "from_hypothesis_only": True},
                bm25_norm=0.0,
                cosine=None,
                token_set_ratio=fuzz.token_set_ratio(query_norm, normalize(name).base_no_accent),
                qualifier_conflict=qualifiers_conflict(query_quals, extract_qualifiers(name)),
            )
        )
    return union


def _cascade_parent_ids(parents: list[ScoredCandidate], decomposed) -> list[str]:
    """Cascade filtresi icin makul parent id listesi: en guclu parent adayi +
    hipotezlerin isaret ettigi parent'lar (sirali, tekrarsiz, MAX_CASCADE_PARENTS)."""
    ordered: list[str] = []
    if parents:
        ordered.append(parents[0].id)
    for hyp in getattr(decomposed, "hypotheses", None) or []:
        if hyp.matched_parent_id is not None:
            ordered.append(hyp.matched_parent_id)
    seen: set[str] = set()
    out: list[str] = []
    for pid in ordered:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out[:MAX_CASCADE_PARENTS]


def resolve(
    query: str,
    *,
    size: int = 10,
    search_fn: PoolSearchFn = _default_search,
    search_knn_fn: PoolSearchFn = _default_search_knn,
    decompose_search_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
) -> ResolveResult:
    """Coklu-hipotezli, recall-yonelimli cascade: her hipotezle parent ara ve
    birlestir, subunit'i makul parent'larin tamamiyla (terms) filtrele +
    filtresizle birlestir (recall-guvenli), her adaya sinyal ekle."""
    dsf = decompose_search_fn or (lambda text, rt: search_fn(text, rt, size=10))
    decomposed = decompose(query, search_fn=dsf)

    parents = _parent_union(
        decomposed, query, size=size, search_fn=search_fn, search_knn_fn=search_knn_fn
    )

    cascade_ids = _cascade_parent_ids(parents, decomposed)

    sub_unfiltered, s_bm25, s_knn, s_max_bm25 = _pool_with_raw_scores(
        query, "subunit", extra_filters=None, size=size, search_fn=search_fn, search_knn_fn=search_knn_fn
    )

    if cascade_ids:
        sub_filtered, sf_bm25, sf_knn, sf_max_bm25 = _pool_with_raw_scores(
            query,
            "subunit",
            extra_filters=[{"terms": {"parent_id": cascade_ids}}],
            size=size,
            search_fn=search_fn,
            search_knn_fn=search_knn_fn,
        )
    else:
        sub_filtered, sf_bm25, sf_knn, sf_max_bm25 = [], {}, {}, 1.0

    sub_merged_raw = _merge_filtered_first(sub_filtered, sub_unfiltered, size=size)
    bm25_by_id = {**s_bm25, **sf_bm25}
    knn_by_id = {**s_knn, **sf_knn}
    max_bm25 = max(s_max_bm25, sf_max_bm25)
    subunits = _attach_signals(
        sub_merged_raw, bm25_by_id=bm25_by_id, knn_by_id=knn_by_id, max_bm25=max_bm25, query_text=query
    )

    return ResolveResult(query=query, decomposed=decomposed, parents=parents, subunits=subunits)
