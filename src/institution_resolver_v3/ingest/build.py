"""Ham CSV -> kanonik JSONL + transform_report.json (deterministik).

Akis: raw_loader -> canonicalize.run_pipeline (P1..P4) -> pydantic modele
serialize -> id'ye gore sirali JSONL + rapor. Ayni girdi ayni bayt cikti.

Sema notu (2026-07-21): P5/P6 kullanici karariyla atlandi; o adimlarin alanlari
onemsiz deger alir (raw_normalized_name = normalized_name, is_evening=False,
hierarchy_context=[]). normalized_name = agresif normalize (keyword eslesme kanali).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from institution_resolver_v3.ingest.canonicalize import run_pipeline
from institution_resolver_v3.ingest.raw_loader import load_parent_rows, load_subunit_rows
from institution_resolver_v3.models import Alias, ParentCanonical, SubunitCanonical
from institution_resolver_v3.normalize.query_pipeline import normalize


def _norm(name: str) -> str:
    return normalize(name).base_no_accent


def _aliases(raw: list[dict[str, Any]]) -> list[Alias]:
    return [Alias(value=a["value"], locale=a.get("locale"), source=a.get("source")) for a in raw]


def _to_parent(r: dict[str, Any]) -> ParentCanonical:
    return ParentCanonical(
        id=r["id"],
        name=r["name"],
        normalized_name=_norm(r["name"]),
        country=r.get("country"),
        city=r.get("city"),
        canonical_ref=r.get("canonical_ref"),
        aliases=_aliases(r.get("aliases", [])),
        active_override=bool(r.get("active_override", False)),
    )


def _to_subunit(r: dict[str, Any]) -> SubunitCanonical:
    norm = _norm(r["name"])
    return SubunitCanonical(
        id=r["id"],
        merged_ids=r["merged_ids"],
        parent_id=r["parent_id"],
        name=r["name"],
        normalized_name=norm,
        raw_normalized_name=norm,           # P5 atlandi: soyma yok -> raw == normalized
        kind_label_raw=r.get("kind_label_raw"),
        unit_type=r.get("unit_type"),
        program_type=r.get("program_type"),
        is_interdisciplinary=bool(r.get("is_interdisciplinary", False)),
        is_evening=False,                   # P5 atlandi (IO tespiti); ertelenmis karar
        is_ror_child=bool(r.get("is_ror_child", False)),
        hierarchy_context=[],               # P6 atlandi
        aliases=_aliases(r.get("aliases", [])),
    )


def _id_key(x: str):
    return int(x) if x.isdigit() else x


def build_data(raw_dir: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Kanonik JSONL + rapor uretir. Doner: transform_report sozlugu."""
    raw_dir = Path(raw_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    parents_raw = load_parent_rows(raw_dir / "institution_parent.csv")
    subs_raw = load_subunit_rows(raw_dir / "institution_subunit.csv")

    parents, subunits, stats = run_pipeline(parents_raw, subs_raw)

    parent_models = sorted((_to_parent(r) for r in parents), key=lambda m: _id_key(m.id))
    subunit_models = sorted((_to_subunit(r) for r in subunits), key=lambda m: _id_key(m.id))

    _write_jsonl(out_dir / "parent_canonical.jsonl", parent_models)
    _write_jsonl(out_dir / "subunit_canonical.jsonl", subunit_models)

    report = {
        "steps": [asdict(s) for s in stats],
        "totals": {
            "parent": len(parent_models),
            "subunit": len(subunit_models),
            "index_total": len(parent_models) + len(subunit_models),
        },
    }
    (out_dir / "transform_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def _write_jsonl(path: Path, models: list[Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for m in models:
            f.write(m.model_dump_json() + "\n")
