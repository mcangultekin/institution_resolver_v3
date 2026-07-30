"""Hakem icin aday paketleme - F4 (bkz. docs/DURUM.md 2026-07-24 tasarim notlari).

Aday paketine `country/city/kind_label/parent_name` alanlari da girer (sahte-ikiz
ve yabanci kurum ayrimi icin). Subunit belgesinde country/city YOK (sadece
parent'ta var, bkz. elastic/document.py) - ES semasina DOKUNULMADAN, subunit'in
`parent_id`'siyle AYNI resolve() cagrisindaki parent aday listesinden JOIN
edilir. Parent listesinde yoksa (subunit'in parent'i hicbir hipotezde aday
olarak cikmadiysa) None kalir - hakem "bilinmiyor" gorur, yanlis deger UYDURULMAZ.

Liste kirpma (2026-07-24, canli bulgu - "Ege University" ornegi): `resolve()`
coklu-hipotez birlesimi (alt hipotez basina +3 aday) uzun/gurultulu bir havuz
uretiyor (18 parent adayi, cogu tamamen alakasiz). Bu havuz `resolve()` icin
DOGRU (recall-yonelimli, gate/decide gibi gelecekteki katmanlar da kullanabilir)
ama HAKEME OLDUGU GIBI verilince zarar veriyor: ayni sorguda dogru cevap
(EGE ÜNİVERSİTESİ, listenin 1. sirasinda, tam_eşleşme=EVET) varken model
listenin sonlarindaki alakasiz bir adayi (Fatih University..., 15. sira)
sectii - ayni aday havuzu 5'e kirpilinca dogru cevabi buldu (canli dogrulandi).
Bu yuzden `build_candidate_views()` SADECE HAKEME giden goruntuyu kirpar -
`resolve()`'un kendi ic havuzu (result.parents/subunits) DEGISMEZ. Kirpma,
`exact_match=True` adaylari SIRALAMADAN BAGIMSIZ garanti tutar (guclu bir
kanit hicbir zaman disari atilmaz), sonra mevcut (recall-guvenli, guclu-once)
sirayla doldurur.
"""

from __future__ import annotations

from dataclasses import dataclass

from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate


@dataclass
class CandidateView:
    """Hakeme gosterilecek aday: sinyaller + baglam alanlari (bkz. modul docstring'i)."""

    id: str
    name: str
    bm25_norm: float
    cosine: float | None
    token_set_ratio: float
    qualifier_conflict: bool
    passed_parent_filter: bool | None
    exact_match: bool = False
    exact_match_text: str | None = None
    best_alias: str | None = None
    country: str | None = None
    city: str | None = None
    kind_label: str | None = None
    parent_name: str | None = None
    parent_id: str | None = None  # subunit'te doldurulur - judge._validate_ids capraz kontrolu icin


def _parent_view(c: ScoredCandidate) -> CandidateView:
    return CandidateView(
        id=c.id,
        name=c.name,
        bm25_norm=c.bm25_norm,
        cosine=c.cosine,
        token_set_ratio=c.token_set_ratio,
        qualifier_conflict=c.qualifier_conflict,
        passed_parent_filter=c.passed_parent_filter,
        exact_match=c.exact_match,
        exact_match_text=c.exact_match_text,
        best_alias=c.best_alias,
        country=c.raw.get("country"),
        city=c.raw.get("city"),
    )


def _subunit_view(c: ScoredCandidate, parent_context: dict[str, ScoredCandidate]) -> CandidateView:
    parent_id = c.raw.get("parent_id")
    parent = parent_context.get(parent_id) if parent_id else None
    return CandidateView(
        id=c.id,
        name=c.name,
        bm25_norm=c.bm25_norm,
        cosine=c.cosine,
        token_set_ratio=c.token_set_ratio,
        qualifier_conflict=c.qualifier_conflict,
        passed_parent_filter=c.passed_parent_filter,
        exact_match=c.exact_match,
        exact_match_text=c.exact_match_text,
        best_alias=c.best_alias,
        country=(parent.raw.get("country") if parent else None),
        city=(parent.raw.get("city") if parent else None),
        kind_label=c.raw.get("kind_label_raw"),
        parent_name=c.raw.get("parent_name"),
        parent_id=parent_id,
    )


def _trim(views: list[CandidateView], max_candidates: int) -> list[CandidateView]:
    """Hakeme giden goruntuyu `max_candidates`e kirpar - `exact_match=True`
    adaylari sirasindan bagimsiz garanti tutar (bkz. modul docstring'i)."""
    if len(views) <= max_candidates:
        return views
    keep_ids: set[str] = {v.id for v in views if v.exact_match}
    for v in views:
        if len(keep_ids) >= max(max_candidates, len(keep_ids)):
            break
        keep_ids.add(v.id)
    # ORIJINAL sira korunur (2026-07-24, Ege/Geriatri bulgusu): kucuk modelde
    # pozisyon yanliligi guclu - exact'leri one tasimak, resolve()'un kendi
    # (guclu-once) siralamasinda 1. olan dogru adayi geriye itip modeli exact'e
    # cekiyordu. exact garanti-tutulur ama YERI degistirilmez.
    return [v for v in views if v.id in keep_ids]


# Hakeme giden aday sayisi ust siniri (parent + subunit ayri ayri) - `resolve()`nin
# kendi ic havuzunu ETKILEMEZ, sadece prompt'a giren goruntuyu kucultur.
DEFAULT_MAX_CANDIDATES = 8


def build_candidate_views(
    result: ResolveResult, *, max_candidates: int = DEFAULT_MAX_CANDIDATES
) -> tuple[list[CandidateView], list[CandidateView]]:
    """(parent_views, subunit_views) - resolve() sonucunu hakem-hazir hale getirir."""
    parent_context = {c.id: c for c in result.parents}
    parents = [_parent_view(c) for c in result.parents]
    subunits = [_subunit_view(c, parent_context) for c in result.subunits]
    return _trim(parents, max_candidates), _trim(subunits, max_candidates)
