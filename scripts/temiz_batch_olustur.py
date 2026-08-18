"""286.948 satirlik gate batch'i (gate_batch_inventory.csv) ile hakeme giden
143.039 satirin duzeltilmis sonucunu (main_batch/birlesik_v4ec_duzeltilmis.csv)
birlestirip sade, tek satir/query'lik bir "temiz" cikti uretir.

Mantik:
  - Taban: gate_batch_inventory.csv (her query icin tek satir).
  - needs_review=0 olan satirlarda (143.909) gate'in kendi karari nihai karardir.
  - needs_review=1 olan satirlarda (143.039) nihai karar
    birlesik_v4ec_duzeltilmis.csv'den gelir (hakem + elle duzeltme).
    Bu satirlardan status=error olanlarda (17.836, hakem gecersiz cevap verdi)
    karar YOK - parent/subunit bos birakilir, match kolonu 'judge_error' olur.

verdict -> match esleme: auto_match->match, no_match->no_match,
review/ambiguous->review (ikisi birlesir), bos->bos (o seviyede aday yok).

Cikti kolonlari: query, normalized_name, parent, parent_id, parent_match,
subunit, subunit_id, subunit_match, parent_json, subunit_json.
parent_json/subunit_json, gate+hakem kanitini (verdict/confidence/decided_by/
signals/aday) tek JSON'da tasir - ayri gate_* / judge_* kolonu YOK.

Kullanim:
    python3 scripts/temiz_batch_olustur.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

csv.field_size_limit(10_000_000)

GATE = Path("main_batch/gate_batch_inventory.csv")
JUDGED = Path("main_batch/birlesik_v4ec_duzeltilmis.csv")
OUT = Path("main_batch/temiz_sonuc.csv")

_VERDICT_TO_MATCH = {
    "auto_match": "match",
    "no_match": "no_match",
    "review": "review",
    "ambiguous": "review",
    "": "",
}


def _map_match(verdict: str) -> str:
    return _VERDICT_TO_MATCH.get(verdict, verdict)


def _side_json(row: dict, side: str, result_json: dict) -> str:
    """side: 'parent' ya da 'subunit'."""
    if row.get("status") == "error":
        payload = {"status": "error", "error": row.get("error", "")}
    else:
        payload = {
            "verdict": row.get(f"{side}_verdict", ""),
            "confidence": row.get(f"{side}_confidence", ""),
            "decided_by": row.get(f"{side}_decided_by", ""),
            "gate": (result_json.get("gate") or {}).get(side),
            "judge": (result_json.get("judge") or {}).get(side),
        }
        cand_id = row.get(f"{side}_cand_id", "")
        if cand_id:
            payload["candidate"] = {
                "id": cand_id,
                "name": row.get(f"{side}_cand_name", ""),
                "confidence": row.get(f"{side}_cand_conf", ""),
            }
        if side == "subunit":
            unit_phrase = row.get("unit_phrase", "")
            if unit_phrase:
                payload["unit_phrase"] = unit_phrase
    return json.dumps(payload, ensure_ascii=False)


def _build_row(base: dict, decision_row: dict) -> dict:
    try:
        result_json = json.loads(decision_row.get("result_json") or "{}")
    except json.JSONDecodeError:
        result_json = {}

    is_error = decision_row.get("status") == "error"

    parent_match = "judge_error" if is_error else _map_match(decision_row.get("parent_verdict", ""))
    subunit_match = "judge_error" if is_error else _map_match(decision_row.get("subunit_verdict", ""))
    parent_blank = is_error or parent_match == "review"
    subunit_blank = is_error or subunit_match == "review"

    return {
        "query": base["query"],
        "normalized_name": base.get("normalized_name", ""),
        "parent": "" if parent_blank else decision_row.get("parent_name", ""),
        "parent_id": "" if parent_blank else decision_row.get("parent_id", ""),
        "parent_match": parent_match,
        "subunit": "" if subunit_blank else decision_row.get("subunit_name", ""),
        "subunit_id": "" if subunit_blank else decision_row.get("subunit_id", ""),
        "subunit_match": subunit_match,
        "parent_json": _side_json(decision_row, "parent", result_json),
        "subunit_json": _side_json(decision_row, "subunit", result_json),
    }


def main() -> None:
    if not GATE.exists():
        raise SystemExit(f"Taban dosya yok: {GATE}")
    if not JUDGED.exists():
        raise SystemExit(f"Hakem/duzeltme dosyasi yok: {JUDGED}")

    with GATE.open(newline="", encoding="utf-8") as f:
        gate_rows = list(csv.DictReader(f))

    with JUDGED.open(newline="", encoding="utf-8") as f:
        judged_rows = {r["query"]: r for r in csv.DictReader(f)}

    fieldnames = [
        "query", "normalized_name",
        "parent", "parent_id", "parent_match",
        "subunit", "subunit_id", "subunit_match",
        "parent_json", "subunit_json",
    ]

    out_rows = []
    missing_in_judged = 0
    error_rows = 0
    for base in gate_rows:
        if base.get("needs_review") == "1":
            decision_row = judged_rows.get(base["query"])
            if decision_row is None:
                missing_in_judged += 1
                decision_row = base  # gate'in kendi review/ambiguous karari kalir
            elif decision_row.get("status") == "error":
                error_rows += 1
        else:
            decision_row = base
        out_rows.append(_build_row(base, decision_row))

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"gate taban satir: {len(gate_rows):,}")
    print(f"hakem/duzeltme satir: {len(judged_rows):,}")
    print(f"birlestirilen (needs_review=1) icinde bulunamayan: {missing_in_judged:,}")
    print(f"hakem hatasi (judge_error): {error_rows:,}")
    print(f"cikti: {OUT} ({len(out_rows):,} satir)")


if __name__ == "__main__":
    main()
