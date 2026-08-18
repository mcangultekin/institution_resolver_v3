"""coverage_weight YENI YANLIS ESLESME uretiyor mu - LLM'siz olcum.

NEDEN (2026-08-17): `scripts/olc_decompose.py` kontrol kumesi yalnizca su an
DOGRU eslesen satirlardan olusuyor, yani "calisani bozuyor mu" sorusunu
cevapliyor. Sormadigi soru: **su an DOGRU olarak `no_match` diyen sorgularda
uydurma eslesme yaratiyor mu?**

Bu, bu projede alti mudahaleyi batiran ornuntudur: bir kisiti gevsetmek dogru
cevabi bazen kurtarir ama "bilmiyorum"u daha sik "eminim ki yanlis"a cevirir.
`coverage_weight` kurum hipotezini tam sorguya dogru ittigi icin, katalogda
karsiligi OLMAYAN bir sorgu artik daha uzun/gercekci bir aralikla aranir -
bos havuz yerine dolu ama yanlis havuz uretebilir.

KUME: ana kosunun `no_match` satirlarindan, sorgunun hicbir ayirt edici
(df<=500, len>=3) tokeni katalogdaki HICBIR kayitta gecmeyenler. Bunlar
katalogda gercekten yok - `no_match` kararlari DOGRU. Olcum bu kararin
korunup korunmadigina bakar; her donus (no_match -> eslesme) muhtemel YENI
HATADIR.

Karar LLM'siz gate ile verilir (deterministik, gun farki sorun degil).
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

from institution_resolver_v3.gate.gate import gate
from institution_resolver_v3.normalize.query_pipeline import normalize
from institution_resolver_v3.retrieve.resolve import resolve
from institution_resolver_v3.retrieve.token_df import (
    DEFAULT_MAX_DF,
    DEFAULT_MIN_LEN,
    load_token_df,
)

csv.field_size_limit(10_000_000)
KOSU = Path("main_batch/birlesik_v4ec.csv")
KATALOG = Path("data/processed/parent_canonical.jsonl")

# Kisa ama GERCEK kurum adlari - coverage_weight kisa araliklari cezalandirdigi
# icin bu sinifi bozma riski var. Ayri kontrol grubu (kucuk, isaret amacli).
AKRONIM_SORGULARI = [
    "MIT", "CERN", "NASA", "TÜBİTAK", "ODTÜ", "İTÜ", "EPFL", "INRIA",
    "Max Planck", "Fraunhofer",
]


def _tok(s: str) -> list[str]:
    return normalize(s).base_no_accent.split()


def kume(n: int) -> list[str]:
    df = load_token_df()
    katalog_tokenlari: set[str] = set()
    with KATALOG.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            metin = [r.get("name") or ""] + [
                a.get("value", "") for a in (r.get("aliases") or [])
            ]
            katalog_tokenlari.update(x for m in metin for x in _tok(m))

    out = []
    with KOSU.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["parent_verdict"] != "no_match":
                continue
            ayirt = [
                t for t in dict.fromkeys(_tok(r["query"]))
                if len(t) >= DEFAULT_MIN_LEN and df.get(t, 0) <= DEFAULT_MAX_DF
            ]
            # Ayirt edici tokenlarin HICBIRI katalogda gecmiyorsa bu kayit
            # katalogda yok demektir -> `no_match` DOGRU.
            if ayirt and not any(t in katalog_tokenlari for t in ayirt):
                out.append(r["query"])
    out.sort(key=lambda q: hashlib.sha256(q.encode()).hexdigest())
    print(f"'kesin no_match' havuzu: {len(out):,} satir -> {min(n, len(out))} orneklendi")
    return out[:n]


def kosu(sorgular: list[str], ad: str, **kw) -> dict[str, str]:
    out = {}
    for q in sorgular:
        g = gate(resolve(q, **kw))
        out[q] = f"{g.parent.verdict}:{g.parent.matched_id or '-'}"
    d = collections.Counter(v.split(":")[0] for v in out.values())
    print(f"  {ad:<14} {dict(d)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--w", type=float, default=0.25)
    a = ap.parse_args()

    sorgular = kume(a.n)

    print("\n=== A) KESIN no_match kumesi - yeni yanlis eslesme sayimi ===")
    taban = kosu(sorgular, "taban")
    yeni = kosu(sorgular, f"w{a.w}", decompose_kwargs={"coverage_weight": a.w})

    donus = [q for q in sorgular
             if taban[q].startswith("no_match") and not yeni[q].startswith("no_match")]
    geri = [q for q in sorgular
            if not taban[q].startswith("no_match") and yeni[q].startswith("no_match")]
    print(f"\n  no_match -> ESLESME : {len(donus)}  (muhtemel YENI HATA)")
    print(f"  eslesme -> no_match : {len(geri)}  (muhtemel duzelme)")
    for q in donus[:12]:
        print(f"     + {q[:56]:<58} {taban[q]} -> {yeni[q]}")

    print("\n=== B) KISA GERCEK adlar - bozuluyor mu ===")
    print(f"  {'sorgu':<14}{'taban':<28}{'w' + str(a.w):<28}")
    for q in AKRONIM_SORGULARI:
        t = gate(resolve(q))
        y = gate(resolve(q, decompose_kwargs={"coverage_weight": a.w}))
        ft = lambda g: f"{g.parent.verdict}/{(g.parent.matched_id or '-')}"  # noqa: E731
        isaret = "  <-- DEGISTI" if ft(t) != ft(y) else ""
        print(f"  {q:<14}{ft(t):<28}{ft(y):<28}{isaret}")


if __name__ == "__main__":
    main()
