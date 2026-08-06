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
   - cosine: gercek kosinus benzerligi. Aday kNN top-K'da gorunduyse ES
     skorundan geri cikarilir (`2*es_score - 1`, `similarity=cosine` mapping);
     gorunmediyse cosine_fn HESAPLAR (hit'in `_source`'undaki embedding ile,
     yoksa mget) - boylece hakem HER aday icin vektor kaniti gorur. `None`
     yalnizca "vektor yok/alinamadi" demektir; 0.0 ile KARISTIRILMAMALI
     (tuketici 0.0 sanip adayi haksiz cezalandirmasin).
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

# (arama metni, kNN listesine girememis hit'ler) -> {raw id -> kosinus}
CosineFn = Callable[[str, list[dict[str, Any]]], dict[str, float]]


def _no_cosine_fn(text: str, hits: list[dict[str, Any]]) -> dict[str, float]:
    """B4 (2026-08-06) varsayilani: kNN'e girmemis adaylar icin kosinus HESAPLANMAZ.

    Kaldirilan is: sorgu basina bir `encode_query` + havuz basina bir `mget` +
    aday basina numpy islemi (olculdu: ~118 ms/sorgu, B2 sonrasi sorgu basina
    6-8 ek mget round-trip'i).

    NEDEN guvenli: bu deger HICBIR karar yoluna girmiyor - `gate` yalnizca
    tsr/exact/span/qualifier kullanir ("bm25/kosinus GIRMEZ", gate.py), hakem
    prompt'undan 2026-07-27'de cikarildi (commit 814437b, e5-base anizotropik:
    alakasiz metin de ~0.78-0.80 aliyor), `decide` hic bakmiyor. Havuz SIRASI da
    etkilenmez: RRF ham bm25/knn listeleriyle calisir, `cosine_fn` ondan SONRA
    kosar ve yalnizca `knn_by_id` sozlugunu doldurur (bkz. _pool_with_raw_scores).
    Kalan tuketiciler yalniz gosterim: CLI tablosu, API alani, CSV kolonu.

    NE KALIYOR: kNN retrieval'in kendisi AYNEN calisir - vektor kanali havuza
    aday sokmaya devam eder (olculdu: parent havuzunun %16.2'si SADECE kNN'den
    geliyor, 120 sorgunun %100'unde en az bir kNN-ozel aday var). kNN top-K'ya
    giren adaylar kosinuslerini BEDAVA almaya devam eder (ES skorundan 2s-1);
    bu fonksiyon yalnizca "listede yoktu, ayrica hesaplayalim" adimini atlar.
    `cosine=None` boylece 2026-07-24 oncesindeki anlamina doner: "kNN listesine
    girmedi". Eski davranis `resolve(..., with_cosine=True)` ile geri gelir.
    """
    return {}


def _default_cosine_fn(text: str, hits: list[dict[str, Any]]) -> dict[str, float]:
    """Havuza girip kNN top-K'da gorunmeyen adaylarin kosinusunu HESAPLAR.

    Arama sonuclari `_source`'ta embedding vektorunu zaten tasir - onlar icin ek
    ES cagrisi yok. Vektoru olmayanlar (enjekte hipotez parent'lari gibi) tek
    mget ile tamamlanir. Doner: gercek kosinus [-1,1]. Vektoru hic bulunamayan
    kayit sozlukte YER ALMAZ (cosine=None kalir - artik "olculemedi" yalnizca
    "vektor yok/alinamadi" demek).
    """
    if not hits:
        return {}
    import numpy as np

    from institution_resolver_v3.elastic.search import fetch_embeddings
    from institution_resolver_v3.embedding.query_encoder import encode_query

    qv = np.asarray(encode_query(text), dtype=np.float32)
    qn = float(np.linalg.norm(qv)) or 1.0

    missing = [h for h in hits if not h.get("embedding")]
    fetched = fetch_embeddings(
        [f"{h.get('record_type', 'parent')}:{h['id']}" for h in missing]
    )
    out: dict[str, float] = {}
    for h in hits:
        vec = h.get("embedding") or fetched.get(h["id"])
        if not vec:
            continue
        v = np.asarray(vec, dtype=np.float32)
        vn = float(np.linalg.norm(v)) or 1.0
        out[h["id"]] = float(np.dot(qv, v) / (qn * vn))
    return out


@dataclass
class ScoredCandidate:
    id: str
    record_type: str
    name: str
    raw: dict[str, Any]
    bm25_norm: float = 0.0
    # None = vektor yok/alinamadi ("dusuk benzerlik" DEGIL). kNN top-K'ya
    # girmeyenler icin kosinus artik cosine_fn ile AYRICA hesaplanir (2026-07-24),
    # o yuzden None nadirdir (embeddingsiz kayit / fetch hatasi).
    cosine: float | None = None
    token_set_ratio: float = 0.0
    qualifier_conflict: bool = False
    passed_parent_filter: bool | None = None  # sadece subunit icin anlamli
    # Adayin ADI ya da ALIAS'LARINDAN BIRI, sorgunun ICINDE ardisik parca
    # olarak geciyorsa True (bkz. _contains_exact - ICERME, tam esitlik degil;
    # token_set_ratio=100 ile KARISTIRILMASIN). 2026-07-24, kullanici talebi -
    # "P" bayragiyla ayni mantik: guclu, ayri bir kanit.
    exact_match: bool = False
    # Sorguya (tsr ile) EN YAKIN alias - adin kendisinden farkliysa dolu. Hakem
    # Turkce katalog adi + Ingilizce sorgu arasinda koprulemeyi bununla yapar
    # (2026-07-24 Gazi/Cardiology bulgusu: "KARDİYOLOJİ ANABİLİM DALI"nin
    # "DIVISION OF CARDIOLOGY" alias'i prompt'ta gorunmeyince model "cardiology"yi
    # kelime cagrisimiyla "KALP VE DAMAR CERRAHİSİ"ne bagladi).
    best_alias: str | None = None
    # exact_match=True ise HANGI normalize ad/alias'in eslestigi - hakem bunun
    # sayesinde eslesmenin sorgunun HANGI parcasini kapsadigini gorur (2026-07-24
    # Ege/Geriatri bulgusu: "Dahili Tip Bilimleri Bolumu"nun alias'i sorgunun
    # sadece orta segmentini karsiliyordu ama hakem bayragi "sorgunun tamaminin
    # karsiligi" sanip daha spesifik dogru adayi (Geriatri) gecti).
    exact_match_text: str | None = None


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
    cosine_fn: CosineFn,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float], float]:
    """BM25+kNN'i AYRI cagirir (ham skorlar korunur), RRF sadece havuzlama/siralama icin.

    kNN top-K'ya girememis havuz uyeleri icin kosinus AYRICA hesaplanir
    (cosine_fn) - hakem her aday icin tam vektor kaniti gorur; "kNN listesine
    girmedi" bilgisi kaybolmaz ama sinyal olarak None birakilmaz.
    """
    bm25_hits = search_fn(text, record_type, extra_filters=extra_filters, size=size)
    knn_hits = search_knn_fn(text, record_type, extra_filters=extra_filters, size=size)
    merged = _rrf_merge([bm25_hits, knn_hits], size=size)
    bm25_by_id = {h["id"]: h["score"] for h in bm25_hits}
    knn_by_id = {h["id"]: h["score"] for h in knn_hits}
    # kNN'de gorunmeyenlerin kosinusu: ES-skor uzayina cevrilip ((c+1)/2)
    # knn_by_id'ye yazilir - _attach_signals tek tip geri-cevirir (2s-1).
    not_in_knn = [h for h in merged if h["id"] not in knn_by_id]
    for hid, cos in cosine_fn(text, not_in_knn).items():
        knn_by_id[hid] = (cos + 1.0) / 2.0
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


def _contains_exact(query_tokens: list[str], candidate_norm: str) -> bool:
    """`candidate_norm` (name/alias, normalize edilmis) sorgu tokenlerinde
    ARDIŞIK bir alt-dizi olarak geciyor mu - kelime siniri gozetir (naif
    Python `in` ile duz karakter-alt-dizgesi KONTROL EDILMEZ; "ana" gibi kisa
    bir ad, "anadolu" gibi baska bir kelimenin ICINDE yanlislikla eslesmesin -
    bkz. decompose.py'deki ayni tuzak). Tam sorgu==ad esitligi DEGIL, ICERME -
    birlesik "kurum+birim" sorgularda kurum adi genelde sorgunun SADECE bir
    parcasidir (2026-07-24, kullanici bulgusu: ilk surum tam-esitlik istiyordu,
    bu yuzden birlesik sorgularda hicbir zaman ates almiyordu)."""
    cand_tokens = candidate_norm.split()
    if not cand_tokens:
        return False
    n = len(cand_tokens)
    return any(query_tokens[i : i + n] == cand_tokens for i in range(len(query_tokens) - n + 1))


def _attach_signals(
    hits: list[dict[str, Any]],
    *,
    bm25_by_id: dict[str, float],
    knn_by_id: dict[str, float],
    max_bm25: float,
    query_text: str,
) -> list[ScoredCandidate]:
    query_norm = normalize(query_text).base_no_accent
    query_tokens = query_norm.split()
    query_quals = extract_qualifiers(query_text)
    out: list[ScoredCandidate] = []
    for h in hits:
        name = h.get("name", "") or ""
        name_norm = normalize(name).base_no_accent
        bm25_raw = bm25_by_id.get(h["id"])
        bm25_norm = (bm25_raw / max_bm25) if bm25_raw is not None else 0.0
        knn_raw = knn_by_id.get(h["id"])
        cosine = (2.0 * knn_raw - 1.0) if knn_raw is not None else None
        conflict = qualifiers_conflict(query_quals, extract_qualifiers(name))
        aliases_raw = h.get("aliases") or []
        alias_norms = {normalize(a).base_no_accent for a in aliases_raw}
        best_alias, best_alias_tsr = None, -1.0
        for a in aliases_raw:
            a_norm = normalize(a).base_no_accent
            if a_norm == name_norm:
                continue
            t = fuzz.token_set_ratio(query_norm, a_norm)
            if t > best_alias_tsr:
                best_alias_tsr, best_alias = t, a
        # tsr = name + HER alias'a karsi ayri ayri hesaplanip EN IYISI alinir -
        # SADECE `name`e bakmak yabanci-dil kacagi yaratiyordu (canli bulundu,
        # 2026-07-24): "Ege Üniversitesi" (TR ad) icin İngilizce sorguda tsr
        # cok dusuk kaliyordu, oysa katalogda "EGE UNIVERSITY" alias'i VARDI -
        # hakem bu yuzden dusuk-tsr'li dogru adayi (Ege) gecip yanlis ama
        # yuksek-tsr'li bir adaya (Fatih University...) auto_match verdi.
        tsr = max(
            [fuzz.token_set_ratio(query_norm, name_norm)]
            + [fuzz.token_set_ratio(query_norm, a) for a in alias_norms]
        )
        exact_text = None
        if _contains_exact(query_tokens, name_norm):
            exact_text = name_norm
        else:
            for a in alias_norms:
                if _contains_exact(query_tokens, a):
                    exact_text = a
                    break
        exact = exact_text is not None
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
                exact_match=exact,
                exact_match_text=exact_text,
                best_alias=best_alias,
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
    cosine_fn: CosineFn,
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
            search_fn=search_fn, search_knn_fn=search_knn_fn, cosine_fn=cosine_fn,
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
    query_tokens = query_norm.split()
    query_quals = extract_qualifiers(query)
    for hyp in decomposed.hypotheses or []:
        pid = hyp.matched_parent_id
        name = hyp.matched_parent_name or ""
        if pid is None or pid in ids_seen:
            continue
        ids_seen.add(pid)
        # enjekte adayin kosinusu da hesaplanir (raw'da embedding yok -> mget yolu);
        # hesaplanamazsa None kalir ("vektor yok/alinamadi").
        cos_map = cosine_fn(hyp.institution_part, [{"id": pid, "record_type": "parent"}])
        inj_name_norm = normalize(name).base_no_accent
        inj_exact = _contains_exact(query_tokens, inj_name_norm)
        union.append(
            ScoredCandidate(
                id=pid,
                record_type="parent",
                name=name,
                raw={"id": pid, "record_type": "parent", "name": name, "from_hypothesis_only": True},
                bm25_norm=0.0,
                cosine=cos_map.get(pid),
                token_set_ratio=fuzz.token_set_ratio(query_norm, inj_name_norm),
                qualifier_conflict=qualifiers_conflict(query_quals, extract_qualifiers(name)),
                exact_match=inj_exact,
                exact_match_text=(inj_name_norm if inj_exact else None),
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
    with_cosine: bool = False,
    search_fn: PoolSearchFn = _default_search,
    search_knn_fn: PoolSearchFn = _default_search_knn,
    decompose_search_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
    cosine_fn: CosineFn | None = None,
) -> ResolveResult:
    """Coklu-hipotezli, recall-yonelimli cascade: her hipotezle parent ara ve
    birlestir, subunit'i makul parent'larin tamamiyla (terms) filtrele +
    filtresizle birlestir (recall-guvenli), her adaya sinyal ekle.

    `with_cosine` (B4, 2026-08-06 - VARSAYILAN KAPALI): kNN top-K'ya girmemis
    adaylar icin kosinusu AYRICA hesaplama adimi. Kapaliyken o adaylarda
    `cosine=None` kalir ("kNN listesine girmedi"); kNN'e girenler kosinusunu
    bedava almaya devam eder. Gerekce ve olcumler `_no_cosine_fn` docstring'inde.
    Gosterim gerektiginde (CLI --debug, API detay) True verilir.

    `cosine_fn` acikca verilirse `with_cosine`den BAGIMSIZ olarak o kullanilir
    (testlerin mevcut sozlesmesi korunur)."""
    if cosine_fn is None:
        cosine_fn = _default_cosine_fn if with_cosine else _no_cosine_fn
    dsf = decompose_search_fn or (lambda text, rt: search_fn(text, rt, size=10))
    # decompose'un O(n^2) span aramasini tek msearch'e topla - AMA yalnizca
    # standart ES yolunda (ozel search_fn/decompose_search_fn enjekte edilmediyse;
    # aksi halde o fn span-basina cagrilarak eski davranis korunur).
    if decompose_search_fn is None and search_fn is _default_search:
        from institution_resolver_v3.elastic.search import search_many

        dsm = lambda texts, rt: search_many(texts, rt, size=10)  # noqa: E731
    else:
        dsm = lambda texts, rt: [dsf(t, rt) for t in texts]  # noqa: E731
    decomposed = decompose(query, search_fn=dsf, search_many_fn=dsm)

    parents = _parent_union(
        decomposed, query, size=size, search_fn=search_fn, search_knn_fn=search_knn_fn,
        cosine_fn=cosine_fn,
    )

    cascade_ids = _cascade_parent_ids(parents, decomposed)

    sub_unfiltered, s_bm25, s_knn, s_max_bm25 = _pool_with_raw_scores(
        query, "subunit", extra_filters=None, size=size, search_fn=search_fn,
        search_knn_fn=search_knn_fn, cosine_fn=cosine_fn,
    )

    if cascade_ids:
        sub_filtered, sf_bm25, sf_knn, sf_max_bm25 = _pool_with_raw_scores(
            query,
            "subunit",
            extra_filters=[{"terms": {"parent_id": cascade_ids}}],
            size=size,
            search_fn=search_fn,
            search_knn_fn=search_knn_fn,
            cosine_fn=cosine_fn,
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
