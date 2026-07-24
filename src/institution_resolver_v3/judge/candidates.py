"""Hakem icin aday paketleme - F4 (bkz. docs/DURUM.md 2026-07-24 tasarim notlari).

Aday paketine `country/city/kind_label/parent_name` alanlari da girer (sahte-ikiz
ve yabanci kurum ayrimi icin). Subunit belgesinde country/city YOK (sadece
parent'ta var, bkz. elastic/document.py) - ES semasina DOKUNULMADAN, subunit'in
`parent_id`'siyle AYNI resolve() cagrisindaki parent aday listesinden JOIN
edilir. Parent listesinde yoksa (subunit'in parent'i hicbir hipotezde aday
olarak cikmadiysa) None kalir - hakem "bilinmiyor" gorur, yanlis deger UYDURULMAZ.
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
    country: str | None = None
    city: str | None = None
    kind_label: str | None = None
    parent_name: str | None = None


def _parent_view(c: ScoredCandidate) -> CandidateView:
    return CandidateView(
        id=c.id,
        name=c.name,
        bm25_norm=c.bm25_norm,
        cosine=c.cosine,
        token_set_ratio=c.token_set_ratio,
        qualifier_conflict=c.qualifier_conflict,
        passed_parent_filter=c.passed_parent_filter,
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
        country=(parent.raw.get("country") if parent else None),
        city=(parent.raw.get("city") if parent else None),
        kind_label=c.raw.get("kind_label_raw"),
        parent_name=c.raw.get("parent_name"),
    )


def build_candidate_views(result: ResolveResult) -> tuple[list[CandidateView], list[CandidateView]]:
    """(parent_views, subunit_views) - resolve() sonucunu hakem-hazir hale getirir."""
    parent_context = {c.id: c for c in result.parents}
    parents = [_parent_view(c) for c in result.parents]
    subunits = [_subunit_view(c, parent_context) for c in result.subunits]
    return parents, subunits
