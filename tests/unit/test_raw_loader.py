"""Adim 0: raw_loader'in gercek ham CSV yapisina karsi davranisini kilitler.

Ham CSV yapisi (2026-07-21 canli dogrulandi):
- parent kolonlari : #, id, name, normalized_name, country, city, iz, top_iz,
  canonical_ref, from_kurum, active, created_at, updated_at, aliases, legacy_institution_ids
- subunit kolonlari: ... parent_id, kind_label ...
- aliases = {"#type": "...", "items": [{"name","locale","source","iz",...}], "anyName": ...}

raw_loader yalniz ihtiyac duydugumuz alanlari ceker; olu kolonlari (iz/top_iz/
created_at...) gormezden gelir. Is mantigi YOK (aktif filtre, merge vb. canonicalize'da).
"""

from __future__ import annotations

import csv
from pathlib import Path

from institution_resolver_v3.ingest.raw_loader import load_parent_rows, load_subunit_rows

_ALIASES_JSON = (
    '{"#type": "App\\\\DTO\\\\Institution\\\\InstitutionAliasListDocument", '
    '"items": [{"iz": null, "name": "GAZI UNIVERSITY", "#type": "x", '
    '"topIz": null, "locale": "en", "source": "legacy_translation"}], '
    '"anyName": null}'
)


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_load_parent_rows_pulls_expected_fields(tmp_path: Path) -> None:
    p = tmp_path / "parent.csv"
    header = ["#", "id", "name", "normalized_name", "country", "city", "iz",
              "top_iz", "canonical_ref", "from_kurum", "active", "created_at",
              "updated_at", "aliases", "legacy_institution_ids"]
    _write_csv(p, header, [
        ["1", "101", "GAZİ ÜNİVERSİTESİ", "gazi universitesi", "TR", "Ankara",
         "", "", "yok:123", "", "true", "", "", _ALIASES_JSON, ""],
    ])
    rows = load_parent_rows(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "101"
    assert r["name"] == "GAZİ ÜNİVERSİTESİ"
    assert r["country"] == "TR"
    assert r["canonical_ref"] == "yok:123"
    assert r["active"] is True
    # olu kolonlar tasinmaz
    assert "iz" not in r and "created_at" not in r
    # aliases: items -> value/locale/source
    assert r["aliases"] == [{"value": "GAZI UNIVERSITY", "locale": "en", "source": "legacy_translation"}]


def test_load_subunit_rows_pulls_parent_id_and_kind_label(tmp_path: Path) -> None:
    p = tmp_path / "subunit.csv"
    header = ["#", "id", "parent_id", "name", "normalized_name", "kind_label",
              "iz", "top_iz", "canonical_ref", "from_kurum", "active",
              "created_at", "updated_at", "aliases", "legacy_institution_ids"]
    _write_csv(p, header, [
        ["1", "5001", "101", "MAKİNE MÜHENDİSLİĞİ BÖLÜMÜ", "makine muhendisligi",
         "Bölüm", "", "", "", "", "false", "", "", _ALIASES_JSON, ""],
    ])
    rows = load_subunit_rows(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["id"] == "5001"
    assert r["parent_id"] == "101"
    assert r["kind_label"] == "Bölüm"
    assert r["active"] is False


def test_empty_aliases_yields_empty_list(tmp_path: Path) -> None:
    p = tmp_path / "parent.csv"
    header = ["#", "id", "name", "normalized_name", "country", "city", "iz",
              "top_iz", "canonical_ref", "from_kurum", "active", "created_at",
              "updated_at", "aliases", "legacy_institution_ids"]
    _write_csv(p, header, [
        ["1", "102", "X ÜNİVERSİTESİ", "x", "TR", "", "", "", "", "", "true",
         "", "", "", ""],
    ])
    assert load_parent_rows(p)[0]["aliases"] == []
