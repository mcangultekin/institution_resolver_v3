"""canonicalize.py P1-P8 adimlarinin test-kilitleri.

Her test docs/V3_VERI_PLANI.md'de olculmus somut vakalari fikstur yapar.
"""

from __future__ import annotations

from institution_resolver_v3.ingest.canonicalize import (
    KIND_LABEL_MAP,
    apply_parent_redirect,
    p1_filter_active_subunits,
    p2_resolve_parent_orphans,
    p3_merge_clones,
    p4_parse_kind_label,
    run_pipeline,
)


# --------------------------------------------------------------------------- #
# P1 — subunit aktif filtre
# --------------------------------------------------------------------------- #
def test_p1_drops_inactive_subunits() -> None:
    rows = [
        {"id": "1", "active": True, "kind_label": "Bölüm"},
        {"id": "2", "active": False, "kind_label": None},   # eski zincir artigi
        {"id": "3", "active": True, "kind_label": "Anabilim Dalı"},
        {"id": "4", "active": False, "kind_label": None},
    ]
    kept, stats = p1_filter_active_subunits(rows)
    assert [r["id"] for r in kept] == ["1", "3"]
    assert stats.step == "P1_subunit_active_filter"
    assert (stats.before, stats.after, stats.dropped) == (4, 2, 2)


def test_p1_is_pure_does_not_mutate_input() -> None:
    rows = [{"id": "1", "active": True}, {"id": "2", "active": False}]
    p1_filter_active_subunits(rows)
    assert len(rows) == 2  # girdi degismedi


def test_p1_treats_missing_active_as_not_active() -> None:
    # Guvenli taraf: active alani yoksa/None ise tutMA (aktiflik acikca True olmali)
    rows = [{"id": "1"}, {"id": "2", "active": None}, {"id": "3", "active": True}]
    kept, _ = p1_filter_active_subunits(rows)
    assert [r["id"] for r in kept] == ["3"]


# --------------------------------------------------------------------------- #
# P2 — parent yetim kurali
# --------------------------------------------------------------------------- #
def _p(pid, name, active, aliases=None):
    return {"id": pid, "name": name, "active": active, "aliases": aliases or []}


def test_p2_drops_inactive_parent_with_no_active_subunit() -> None:
    # DURUM 1: inaktif + altinda aktif subunit yok -> dusur (gercekte 147 kayit)
    parents = [_p("1", "AKTIF UNI", True), _p("99", "OLU UNI", False)]
    kept, redirect, stats = p2_resolve_parent_orphans(parents, active_subunit_parent_ids=set())
    assert [r["id"] for r in kept] == ["1"]
    assert redirect == {}
    assert stats.dropped == 1


def test_p2_redirects_bilkent_305_to_150() -> None:
    # DURUM 2: dokumante gercek vaka - Bilkent 305 -> Ihsan Dogramaci Bilkent 150
    parents = [
        _p("150", "İHSAN DOĞRAMACI BİLKENT ÜNİVERSİTESİ", True),
        _p("305", "BİLKENT ÜNİVERSİTESİ", False),
    ]
    kept, redirect, stats = p2_resolve_parent_orphans(
        parents, active_subunit_parent_ids={"305"}
    )
    assert redirect == {"305": "150"}                 # subunit'ler 150'ye devredilecek
    assert [r["id"] for r in kept] == ["150"]         # 305 korpustan cikti
    # inaktif ad hedefe alias olarak enjekte edildi (insanlarin yazdigi ad)
    target = next(r for r in kept if r["id"] == "150")
    assert any(a["value"] == "BİLKENT ÜNİVERSİTESİ" for a in target["aliases"])


def test_p2_keeps_override_when_no_active_match() -> None:
    # DURUM 3: dokumante gercek vakalar - 239/356/118 aktif karsiligi yok, korunur
    parents = [
        _p("1", "BASKA UNI", True),
        _p("239", "ANKA TEKNOLOJİ ÜNİVERSİTESİ", False),
        _p("118", "KIBRIS SOSYAL BİLİMLER ÜNİVERSİTESİ", False),
    ]
    kept, redirect, stats = p2_resolve_parent_orphans(
        parents, active_subunit_parent_ids={"239", "118"}
    )
    assert redirect == {}
    kept_ids = {r["id"] for r in kept}
    assert kept_ids == {"1", "239", "118"}            # muaflar korpusta kaldi
    for r in kept:
        if r["id"] in {"239", "118"}:
            assert r["active_override"] is True
    assert set(stats.notes["override"]) == {"239", "118"}


def test_p2_active_parents_pass_through_unchanged() -> None:
    parents = [_p("1", "A UNI", True), _p("2", "B UNI", True)]
    kept, redirect, stats = p2_resolve_parent_orphans(parents, active_subunit_parent_ids=set())
    assert {r["id"] for r in kept} == {"1", "2"}
    assert redirect == {}
    assert stats.dropped == 0


def test_p2_no_midtoken_false_redirect() -> None:
    # "ege universitesi" -> "egem universitesi" gibi mid-token eslesme OLMAMALI
    parents = [
        _p("1", "EGEM ÜNİVERSİTESİ", True),
        _p("77", "GEM ÜNİVERSİTESİ", False),   # "gem universitesi" mid-token, kapsanmamali
    ]
    kept, redirect, stats = p2_resolve_parent_orphans(parents, active_subunit_parent_ids={"77"})
    assert redirect == {}                        # yanlis devir yok
    assert next(r for r in kept if r["id"] == "77")["active_override"] is True


# --------------------------------------------------------------------------- #
# P2->P3 koprusu — redirect uygulama
# --------------------------------------------------------------------------- #
def test_apply_parent_redirect_moves_subunit_parent_id() -> None:
    subs = [
        {"id": "10", "parent_id": "305", "name": "X"},   # Bilkent inaktif
        {"id": "11", "parent_id": "42", "name": "Y"},    # etkilenmez
    ]
    out = apply_parent_redirect(subs, {"305": "150"})
    assert out[0]["parent_id"] == "150"
    assert out[1]["parent_id"] == "42"
    assert subs[0]["parent_id"] == "305"                 # girdi degismedi (saf)


# --------------------------------------------------------------------------- #
# P3 — klon merge
# --------------------------------------------------------------------------- #
def _s(sid, parent_id, name, kind, aliases=None):
    return {"id": sid, "parent_id": parent_id, "name": name, "kind_label": kind,
            "aliases": aliases or [{"value": name, "locale": "tr", "source": "legacy_row"}]}


def test_p3_merges_identical_clones_into_smallest_id() -> None:
    # SBU-tipi: birebir ozdes 3 kayit -> 1, merged_ids hepsi, kanonik en kucuk id
    rows = [
        _s("300", "49", "ALGOLOJİ BİLİM DALI", "Bilim Dalı"),
        _s("100", "49", "ALGOLOJİ BİLİM DALI", "Bilim Dalı"),
        _s("200", "49", "ALGOLOJİ BİLİM DALI", "Bilim Dalı"),
    ]
    merged, stats = p3_merge_clones(rows)
    assert len(merged) == 1
    assert merged[0]["id"] == "100"                       # en kucuk id kanonik
    assert merged[0]["merged_ids"] == ["100", "200", "300"]
    assert stats.notes["merged_groups"] == 1
    assert stats.notes["absorbed_rows"] == 2


def test_p3_does_not_merge_different_kind_label() -> None:
    # Gazi istatistik: ayni ad, FARKLI kind -> birlesMEZ
    rows = [
        _s("1", "101", "İSTATİSTİK", "Bölüm"),
        _s("2", "101", "İSTATİSTİK", "Lisans"),
        _s("3", "101", "İSTATİSTİK", "Doktora Programı"),
    ]
    merged, stats = p3_merge_clones(rows)
    assert len(merged) == 3
    assert stats.notes["absorbed_rows"] == 0
    for m in merged:
        assert m["merged_ids"] == [m["id"]]              # tekil: merged_ids=[kendi]


def test_p3_does_not_merge_when_aliases_differ() -> None:
    # Bankacilik-tipi: parent+ad+kind ayni ama alias FARKLI -> ayri kalir (kullanici onayi)
    rows = [
        _s("73393", "364", "BANKACILIK VE SİGORTACILIK BÖLÜMÜ", "Bölüm",
           aliases=[{"value": "FİNANS BANKACILIK VE SİGORTACILIK", "locale": "tr", "source": "legacy_row"}]),
        _s("73448", "364", "BANKACILIK VE SİGORTACILIK BÖLÜMÜ", "Bölüm",
           aliases=[{"value": "BANKACILIK VE SİGORTACILIK", "locale": "tr", "source": "legacy_row"}]),
    ]
    merged, _ = p3_merge_clones(rows)
    assert len(merged) == 2                               # ayri kaldi


def test_p3_ignores_source_locale_in_identity() -> None:
    # Ayni alias DEGERI ama farkli source -> KIMLIK ayni, birlesir; alias union'da ikisi de
    rows = [
        _s("2", "9", "TARİH", "Bölüm", aliases=[{"value": "TARİH", "locale": "tr", "source": "ror"}]),
        _s("1", "9", "TARİH", "Bölüm", aliases=[{"value": "TARİH", "locale": "tr", "source": "legacy_row"}]),
    ]
    merged, _ = p3_merge_clones(rows)
    assert len(merged) == 1
    assert merged[0]["id"] == "1"
    sources = {a["source"] for a in merged[0]["aliases"]}
    assert sources == {"ror", "legacy_row"}              # alias union kayipsiz


# --------------------------------------------------------------------------- #
# P4 — kind_label ayristirma
# --------------------------------------------------------------------------- #
def test_p4_map_has_all_24_values() -> None:
    assert len(KIND_LABEL_MAP) == 24


def test_p4_parses_representative_values() -> None:
    rows = [
        {"id": "1", "kind_label": "Bölüm"},
        {"id": "2", "kind_label": "Tezli Yüksek Lisans Programı"},
        {"id": "3", "kind_label": "Tezsiz Yüksek Lisans Programı"},
        {"id": "4", "kind_label": "Doktora Programı"},
        {"id": "5", "kind_label": "Disiplinlerarası Tezli Yüksek Lisans Programı"},
        {"id": "6", "kind_label": "ror_child"},
    ]
    out, stats = p4_parse_kind_label(rows)
    by = {r["id"]: r for r in out}
    # Bölüm -> unit_type, program_type yok
    assert by["1"]["unit_type"] == "bolum" and by["1"]["program_type"] is None
    # Tezli / Tezsiz ZIT (embedding ayirt edemez, sert kural burada mumkun olur)
    assert by["2"]["program_type"] == "tezli_yl"
    assert by["3"]["program_type"] == "tezsiz_yl"
    assert by["4"]["program_type"] == "doktora"
    # Disiplinlerarasi -> program_type + interdis bayragi
    assert by["5"]["program_type"] == "tezli_yl" and by["5"]["is_interdisciplinary"] is True
    # ror_child -> unit_type + bayrak
    assert by["6"]["unit_type"] == "ror_child" and by["6"]["is_ror_child"] is True
    # ham deger korunur
    assert by["1"]["kind_label_raw"] == "Bölüm"
    assert stats.notes["unknown_kind_labels"] == {}


def test_p4_unknown_kind_label_is_reported_not_silent() -> None:
    rows = [{"id": "1", "kind_label": "Yeni Tuhaf Tur"}]
    out, stats = p4_parse_kind_label(rows)
    assert out[0]["unit_type"] is None and out[0]["program_type"] is None
    assert stats.notes["unknown_kind_labels"] == {"Yeni Tuhaf Tur": 1}


def test_p4_is_pure() -> None:
    rows = [{"id": "1", "kind_label": "Bölüm"}]
    p4_parse_kind_label(rows)
    assert "unit_type" not in rows[0]              # girdi degismedi


# --------------------------------------------------------------------------- #
# Orchestrator — P1..P4 birlikte
# --------------------------------------------------------------------------- #
def test_run_pipeline_composes_all_steps() -> None:
    parents = [
        _p("150", "İHSAN DOĞRAMACI BİLKENT ÜNİVERSİTESİ", True),
        _p("305", "BİLKENT ÜNİVERSİTESİ", False),   # -> 150'ye devir
        _p("49", "SAĞLIK BİLİMLERİ ÜNİVERSİTESİ", True),
        _p("900", "OLU ÜNİVERSİTE", False),          # altinda aktif yok -> dus
    ]
    subs = [
        {"id": "10", "parent_id": "305", "name": "TIP", "kind_label": "Bölüm",
         "active": True, "aliases": [{"value": "TIP", "locale": "tr", "source": "legacy_row"}]},
        # SBU 2 ozdes klon -> 1
        _clone("100", "49", "ALGOLOJİ BİLİM DALI"),
        _clone("200", "49", "ALGOLOJİ BİLİM DALI"),
        # inaktif subunit -> dus
        {"id": "300", "parent_id": "49", "name": "X", "kind_label": "Bölüm",
         "active": False, "aliases": []},
    ]
    parents_out, subs_out, stats = run_pipeline(parents, subs)

    parent_ids = {r["id"] for r in parents_out}
    assert parent_ids == {"150", "49"}               # 305 devredildi, 900 dustu
    # subunit: TIP (305->150'ye tasindi) + ALGOLOJI (2->1 merge) = 2 kayit
    assert len(subs_out) == 2
    tip = next(r for r in subs_out if r["name"] == "TIP")
    assert tip["parent_id"] == "150"                 # redirect uygulandi
    alg = next(r for r in subs_out if "ALGOLOJİ" in r["name"])
    assert alg["merged_ids"] == ["100", "200"]       # merge
    assert alg["unit_type"] == "bilim_dali"          # P4 calisti
    assert [s.step for s in stats] == [
        "P1_subunit_active_filter", "P2_parent_orphan_rule",
        "P3_clone_merge", "P4_kind_label_parse",
    ]


def _clone(sid, parent_id, name):
    return {"id": sid, "parent_id": parent_id, "name": name, "kind_label": "Bilim Dalı",
            "active": True, "aliases": [{"value": name, "locale": "tr", "source": "legacy_row"}]}
