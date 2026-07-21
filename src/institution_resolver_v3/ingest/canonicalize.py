"""Ham kayit -> kanonik kayit donusumu (P1-P8). Saf fonksiyonlar.

Kaynak dogrusu: docs/V3_VERI_PLANI.md. Her P adimi ayri, yan-etkisiz bir
fonksiyondur; her biri (sonuc, StepStats) dondurur ki profile.py raporu her
adimin once/sonra sayilarini toplayabilsin.

Adim sirasi (bagimlilik):
  P1 subunit aktif filtre (kosulsuz)
  P2 parent yetim kurali (kosullu)
  P3 klon birlestir  <- merge anahtari SOYMA ONCESI ada gore (P5'ten once)
  P4 kind_label ayristirma
  P5 ad temizligi + qualifier soyma
  P6 zincirli ad normalizasyonu
  P7 olu kolonlar (sema disi birakma - ayri fonksiyon gerekmez)
  P8 ror_child bayragi

DIKKAT (V3_VERI_PLANI Bolum 2 §3 notu): P5 qualifier soyma normalized_name'i
degistirir; P3 merge anahtari soyma ONCESI ada gore kurulur, yoksa (IO) ikizleri
ve tezli/tezsiz yanlislikla birlesir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from institution_resolver_v3.normalize.query_pipeline import normalize


@dataclass
class StepStats:
    """Bir P adiminin once/sonra sayilari + istisna ornekleri (rapor icin)."""

    step: str
    before: int
    after: int
    dropped: int = 0
    notes: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# P1 — Subunit aktif filtre (KOSULSUZ)
# --------------------------------------------------------------------------- #
def p1_filter_active_subunits(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], StepStats]:
    """active=False subunit satirlarini kosulsuz atar.

    Olcum (V3_VERI_PLANI P1): 179.106 -> 138.298; dusen 40.808'in %99.3'u eski
    zincirli-ad artigi, hepsinin kind_label'i bos, altlarinda kimse yok.
    Bu fonksiyon yalniz filtreler; 'kind_label bos mu' iddiasi rapor/testin isi.
    """
    kept = [r for r in rows if r.get("active") is True]
    stats = StepStats(
        step="P1_subunit_active_filter",
        before=len(rows),
        after=len(kept),
        dropped=len(rows) - len(kept),
    )
    return kept, stats


# --------------------------------------------------------------------------- #
# P2 — Parent yetim (oksuz) kurali (KOSULLU)
# --------------------------------------------------------------------------- #
def _norm_name(name: str) -> str:
    """Ad karsilastirmasi icin aksansiz normalize (P2 devir eslesmesi)."""
    return normalize(name).base_no_accent


def _token_contains(haystack: str, needle: str) -> bool:
    """`needle`, `haystack` icinde TOKEN sinirinda geciyor mu (mid-token degil).

    Ornek: "bilkent universitesi", "ihsan dogramaci bilkent universitesi"
    icinde token-sinirli geciyor -> True.
    """
    if haystack == needle:
        return True
    return (
        haystack.startswith(needle + " ")
        or haystack.endswith(" " + needle)
        or (" " + needle + " ") in haystack
    )


def p2_resolve_parent_orphans(
    parent_rows: list[dict[str, Any]],
    active_subunit_parent_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, str], StepStats]:
    """Inaktif parent'lari uc duruma ayirir (V3_VERI_PLANI P2; ham veride dogrulandi).

    Kural (inaktif parent icin):
      1. Altinda aktif subunit YOK           -> dusur.
      2. Altinda aktif subunit VAR + adi bir aktif parent'in adina esit ya da
         onun icinde token-sinirli geciyor  -> subunit'leri o aktif parent'a
         DEVRET (redirect_map), inaktif adi hedefe alias olarak ekle.
      3. Altinda aktif subunit VAR ama aktif karsilik YOK -> active_override=True
         ile KORU (aksi halde subunit'leri yetim kalir).
    Aktif parent'lar oldugu gibi gecer (redirect alias enjeksiyonu haric).

    Donen redirect_map {eski_parent_id: yeni_parent_id} subunit tarafina SONRA
    uygulanir (bu fonksiyon subunit'e dokunmaz - katman ayrimi).

    Olculen gercek (2026-07-21): 151 inaktif -> 147 dusur, 1 devir (305->150),
    3 muaf (239/356/118), 52 etkilenen subunit.
    """
    # aktif parent adlarinin normalize indeksi
    active_index: dict[str, list[str]] = {}
    kept_by_id: dict[str, dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for r in parent_rows:
        if r.get("active") is True:
            active_index.setdefault(_norm_name(r["name"]), []).append(r["id"])
            kept.append(r)
            kept_by_id[r["id"]] = r

    redirect_map: dict[str, str] = {}
    dropped_ids: list[str] = []
    override_ids: list[str] = []
    redirects: list[tuple[str, str]] = []

    for r in parent_rows:
        if r.get("active") is True:
            continue
        pid = r["id"]
        if pid not in active_subunit_parent_ids:
            dropped_ids.append(pid)
            continue
        norm = _norm_name(r["name"])
        cand = list(active_index.get(norm, []))
        if not cand:
            for a_norm, ids in active_index.items():
                if _token_contains(a_norm, norm):
                    cand += ids
        if cand:
            target = min(cand, key=lambda x: int(x) if x.isdigit() else x)
            redirect_map[pid] = target
            redirects.append((pid, target))
            _inject_alias(kept_by_id[target], r["name"])
        else:
            override = {**r, "active_override": True}
            override_ids.append(pid)
            kept.append(override)
            kept_by_id[pid] = override

    stats = StepStats(
        step="P2_parent_orphan_rule",
        before=len(parent_rows),
        after=len(kept),
        dropped=len(dropped_ids),
        notes={
            "redirect": redirects,
            "override": override_ids,
            "dropped_sample": dropped_ids[:10],
        },
    )
    return kept, redirect_map, stats


def _inject_alias(target: dict[str, Any], name: str) -> None:
    """Devredilen inaktif parent adini hedefe alias olarak ekler (dedup'lu).

    "Bilkent Universitesi" gibi - insanlarin yazdigi ad, hedefte yoksa degerli.
    """
    aliases = target.setdefault("aliases", [])
    existing = {_norm_name(a.get("value", "")) for a in aliases}
    if _norm_name(name) not in existing:
        aliases.append({"value": name, "locale": None, "source": "orphan_redirect"})


# --------------------------------------------------------------------------- #
# P2->P3 koprusu — redirect_map'i subunit parent_id'sine uygula
# --------------------------------------------------------------------------- #
def apply_parent_redirect(
    subunit_rows: list[dict[str, Any]],
    redirect_map: dict[str, str],
) -> list[dict[str, Any]]:
    """P2'nin redirect_map'ini subunit'lere uygular (parent_id devri).

    Ornek: parent_id=305 (Bilkent, inaktif) -> 150. P3 merge'den ONCE
    calismali ki devredilen subunit dogru parent altinda gruplansin.
    Saf: yeni liste doner, girdiyi degistirmez.
    """
    if not redirect_map:
        return list(subunit_rows)
    out = []
    for r in subunit_rows:
        new_pid = redirect_map.get(r["parent_id"])
        out.append({**r, "parent_id": new_pid} if new_pid else r)
    return out


# --------------------------------------------------------------------------- #
# P3 — Klon-merge (birebir ayni kayitlari tekle)
# --------------------------------------------------------------------------- #
def _alias_value_sig(aliases: list[dict[str, Any]]) -> frozenset[str]:
    """Alias DEGER kumesi (normalize'li). source/locale KIMLIK degil, disarda."""
    return frozenset(_norm_name(a.get("value", "")) for a in aliases)


def _union_aliases(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Birlesen uyelerin alias'larini birlestirir, (value, locale, source) tam
    ikizlerini eler. (normalize-degeri dedup'u P4 4a'nin isi - burada degil.)"""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for m in members:
        for a in m.get("aliases", []):
            k = (a.get("value"), a.get("locale"), a.get("source"))
            if k not in seen:
                seen.add(k)
                out.append(a)
    return out


def _id_key(x: str):
    return int(x) if x.isdigit() else x


def p3_merge_clones(
    subunit_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], StepStats]:
    """Birebir ayni subunit kayitlarini tek kanonik kayda indirir + merged_ids.

    Birlesme anahtari (KULLANICI ONAYI 2026-07-21, alias-farkindalikli):
        (parent_id, normalize(name).base_no_accent, kind_label, alias-DEGER-kumesi)
    Alias'i farkli olan kayitlar (parent/ad/kind ayni olsa da) AYRI kalir
    (Bankacilik-tipi 193 kayit; over-merge geri donulemez bilgi kaybi olurdu).

    Kanonik id = grubun en kucuk id'si; merged_ids = grubun TUM id'leri (kendisi
    dahil), sirali. Tekil kayitta merged_ids = [kendi id].

    Olculen (ham veri, 2026-07-21): 138298 aktif -> 125108 cikti, 5034 grup
    birlesti, 13190 satir emildi. (Gazi'nin 11 istatistik'i kind_label farki
    ile BIRLESMEZ; SBU'nun ~174 ozdes kaydi tek kayda iner.)
    """
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in subunit_rows:
        key = (
            r["parent_id"],
            _norm_name(r["name"]),
            r.get("kind_label"),
            _alias_value_sig(r.get("aliases", [])),
        )
        groups.setdefault(key, []).append(r)

    merged: list[dict[str, Any]] = []
    n_merged_groups = 0
    n_absorbed = 0
    for members in groups.values():
        members_sorted = sorted(members, key=lambda r: _id_key(r["id"]))
        canonical = {**members_sorted[0]}
        canonical["merged_ids"] = sorted((m["id"] for m in members), key=_id_key)
        if len(members) > 1:
            n_merged_groups += 1
            n_absorbed += len(members) - 1
            canonical["aliases"] = _union_aliases(members_sorted)
        merged.append(canonical)

    stats = StepStats(
        step="P3_clone_merge",
        before=len(subunit_rows),
        after=len(merged),
        dropped=n_absorbed,
        notes={"merged_groups": n_merged_groups, "absorbed_rows": n_absorbed},
    )
    return merged, stats


# --------------------------------------------------------------------------- #
# P4 — kind_label ayristirma (24 ham deger -> yapilandirilmis alanlar)
# --------------------------------------------------------------------------- #
# (unit_type, program_type, is_interdisciplinary, is_ror_child)
# Kaynak: V3_VERI_PLANI §3; 24 deger ham veride birebir dogrulandi (2026-07-21).
KIND_LABEL_MAP: dict[str, tuple[str | None, str | None, bool, bool]] = {
    "Anabilim Dalı": ("anabilim_dali", None, False, False),
    "Bölüm": ("bolum", None, False, False),
    "ror_child": ("ror_child", None, False, True),
    "Lisans": (None, "lisans", False, False),
    "Tezli Yüksek Lisans Programı": (None, "tezli_yl", False, False),
    "Önlisans": (None, "onlisans", False, False),
    "Bilim Dalı": ("bilim_dali", None, False, False),
    "Doktora Programı": (None, "doktora", False, False),
    "Uygulama ve Araştırma Merkezi": ("uygar_merkezi", None, False, False),
    "Tezsiz Yüksek Lisans Programı": (None, "tezsiz_yl", False, False),
    "Fakülte": ("fakulte", None, False, False),
    "Disiplinlerarası Anabilim Dalı": ("anabilim_dali", None, True, False),
    "Disiplinlerarası Tezli Yüksek Lisans Programı": (None, "tezli_yl", True, False),
    "Meslek Yüksekokulu": ("myo", None, False, False),
    "Anasanat Dalı": ("anasanat_dali", None, False, False),
    "Disiplinlerarası Tezsiz Yüksek Lisans Programı": (None, "tezsiz_yl", True, False),
    "Enstitü": ("enstitu", None, False, False),
    "Disiplinlerarası Doktora Programı": (None, "doktora", True, False),
    "Sanat Dalı": ("sanat_dali", None, False, False),
    "Yüksekokul": ("yuksekokul", None, False, False),
    "Rektörlük": ("rektorluk", None, False, False),
    "Sanatta Yeterlik Programı": (None, "sanatta_yeterlik", False, False),
    "Disiplinlerarası Sanatta Yeterlik Programı": (None, "sanatta_yeterlik", True, False),
    "Disiplinlerarası Anasanat Dalı": ("anasanat_dali", None, True, False),
}


def p4_parse_kind_label(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], StepStats]:
    """Ham `kind_label`'i yapilandirilmis alanlara ayristirir.

    Cikan alanlar (her kayda eklenir):
      kind_label_raw, unit_type, program_type, is_interdisciplinary, is_ror_child.
    Iki eksen birbirini dislar: bir kayit ya unit_type (bolum/anabilim_dali...)
    ya program_type (lisans/tezli_yl/doktora...) tasir.

    Bilinmeyen kind_label (yeni dump'ta 25. deger) -> alanlar None, rapora yazilir
    (sessiz gecmez - konvansiyon degisim dedektoru, V3_VERI_PLANI P9).
    """
    out: list[dict[str, Any]] = []
    unknown: dict[str, int] = {}
    for r in rows:
        raw = r.get("kind_label")
        mapping = KIND_LABEL_MAP.get(raw)
        if mapping is None:
            unknown[raw] = unknown.get(raw, 0) + 1
            unit_type = program_type = None
            is_interdisc = is_ror = False
        else:
            unit_type, program_type, is_interdisc, is_ror = mapping
        out.append({
            **r,
            "kind_label_raw": raw,
            "unit_type": unit_type,
            "program_type": program_type,
            "is_interdisciplinary": is_interdisc,
            "is_ror_child": is_ror,
        })
    stats = StepStats(
        step="P4_kind_label_parse",
        before=len(rows),
        after=len(out),
        notes={"unknown_kind_labels": unknown},
    )
    return out, stats


# --------------------------------------------------------------------------- #
# Orchestrator — P1..P4'u sirayla baglar
# --------------------------------------------------------------------------- #
def run_pipeline(
    parent_rows: list[dict[str, Any]],
    subunit_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[StepStats]]:
    """Ham parent+subunit dict listelerini kanonik kayitlara donusturur.

    Akis: P1 (aktif filtre) -> aktif-subunit-parent-id kumesi -> P2 (yetim kurali,
    redirect_map) -> redirect'i subunit'e uygula -> P3 (klon-merge) -> P4 (kind_label).

    P5/P6 KULLANICI KARARIYLA ATLANDI (2026-07-21): qualifier soyma gereksiz
    (bilgi P4'te), zincirli-ad Turkce cop formati aktif veride yok.

    Doner: (kanonik_parentlar, kanonik_subunitler, adim_istatistikleri).
    """
    stats: list[StepStats] = []

    active_subs, s1 = p1_filter_active_subunits(subunit_rows)
    stats.append(s1)

    active_sub_parent_ids = {r["parent_id"] for r in active_subs}
    parents, redirect_map, s2 = p2_resolve_parent_orphans(parent_rows, active_sub_parent_ids)
    stats.append(s2)

    active_subs = apply_parent_redirect(active_subs, redirect_map)

    merged_subs, s3 = p3_merge_clones(active_subs)
    stats.append(s3)

    subunits, s4 = p4_parse_kind_label(merged_subs)
    stats.append(s4)

    return parents, subunits, stats
