"""decompose duzeltme adaylarini olcer - LLM'siz, havuz seviyesinde.

NEDEN BU METRIK: gold yok ve yargi gerektiren metrikler bu projede
kalibre edilemedi. Onun yerine NESNEL soru soruluyor:
**beklenen kayit resolve() havuzuna girdi mi, girdiyse kacinci sirada?**
Hakem havuzu 8'e kirpilmis halde gordugu icin "ilk 8" esik olarak kullanilir.

IKI KUME - biri olmadan olcum yaniltir:
  HEDEF  : su an yanlis `no_match` olan, dogru cevabi katalogda APACIK duran
           sorgular. Duzeltme bunlari KURTARMALI.
  KONTROL: su an `auto_match` alan sorgular. Duzeltme bunlari BOZMAMALI.
Bu projede yedi mudahalenin altisi hedefte kazanip kontrolde daha cok
kaybetmisti; tek kume ile olculse hepsi basarili gorunurdu.

HEDEF kumesinin "dogru cevabi" gold degil, token-kapsama turevi:
sorgunun TUM ayirt edici (df<=500, len>=3) tokenlarini tasiyan katalog
kaydi. Elle bakildiginda bu kovanin ~%50'si gercek eslesme (2026-08-17,
15 ornek). Yani mutlak sayilar degil, ADAYLAR ARASI FARK anlamlidir.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

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
KUME = Path("data/eval/decompose_olcum_kumesi.json")
TRIM = 8  # hakemin gordugu aday sayisi


def _tok(s: str) -> list[str]:
    return normalize(s).base_no_accent.split()


def _ters_indeks(df: dict[str, int]):
    ters: dict[str, set[str]] = collections.defaultdict(set)
    with KATALOG.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            metin = [r.get("name") or ""] + [
                a.get("value", "") for a in (r.get("aliases") or [])
            ]
            for t in {x for m in metin for x in _tok(m)}:
                if df.get(t, 0) <= DEFAULT_MAX_DF and len(t) >= DEFAULT_MIN_LEN:
                    ters[t].add(r["id"])
    return ters


def kume_olustur(n_hedef: int, n_kontrol: int) -> dict:
    """Iki kumeyi kurar ve DISKE YAZAR - adaylar ayni kume uzerinde olculsun."""
    import hashlib

    df = load_token_df()
    ters = _ters_indeks(df)

    hedef, kontrol, alt_kontrol = [], [], []
    with KOSU.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v = r["parent_verdict"]
            if v == "auto_match" and r["parent_id"]:
                kontrol.append({"query": r["query"], "beklenen": r["parent_id"]})
                # SUBUNIT KONTROLU: coverage_weight kurum hipotezini tam
                # sorguya dogru itiyor, yani `unit_part` bosaliyor. Birim
                # eslestirmesi ona dayandigi icin parent'ta kazanip subunit'te
                # kaybetme riski var - olculmeden benimsenemez.
                if r["subunit_verdict"] == "auto_match" and r["subunit_id"]:
                    alt_kontrol.append({"query": r["query"], "beklenen": r["subunit_id"]})
            elif v == "no_match":
                ayirt = [
                    t for t in dict.fromkeys(_tok(r["query"]))
                    if len(t) >= DEFAULT_MIN_LEN and df.get(t, 0) <= DEFAULT_MAX_DF
                ]
                if len(ayirt) < 2:
                    continue
                say: collections.Counter[str] = collections.Counter()
                for t in ayirt:
                    for pid in ters.get(t, ()):
                        say[pid] += 1
                if not say:
                    continue
                pid, kac = say.most_common(1)[0]
                if kac == len(ayirt):
                    hedef.append({"query": r["query"], "beklenen": pid})

    anahtar = lambda d: hashlib.sha256(d["query"].encode()).hexdigest()  # noqa: E731
    kume = {
        "hedef": sorted(hedef, key=anahtar)[:n_hedef],
        "kontrol": sorted(kontrol, key=anahtar)[:n_kontrol],
        "alt_kontrol": sorted(alt_kontrol, key=anahtar)[:n_kontrol],
    }
    KUME.parent.mkdir(parents=True, exist_ok=True)
    KUME.write_text(json.dumps(kume, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"hedef {len(kume['hedef'])} · kontrol {len(kume['kontrol'])} · alt_kontrol {len(kume['alt_kontrol'])} -> {KUME}")
    return kume


def olc(kume: dict, ad: str, **kw) -> dict:
    """Bir yapilandirmayi iki kumede kosar; havuza girme/ilk-8 sayar."""
    out = {}
    for grup in ("hedef", "kontrol", "alt_kontrol"):
        havuzda = ilk8 = 0
        siralar = []
        for kayit in kume[grup]:
            r = resolve(kayit["query"], **kw)
            # alt_kontrol subunit havuzuna bakar; digerleri parent havuzuna.
            ids = [c.id for c in (r.subunits if grup == "alt_kontrol" else r.parents)]
            if kayit["beklenen"] in ids:
                havuzda += 1
                s = ids.index(kayit["beklenen"]) + 1
                siralar.append(s)
                if s <= TRIM:
                    ilk8 += 1
        n = len(kume[grup]) or 1
        out[grup] = {
            "n": len(kume[grup]),
            "havuzda": havuzda,
            "ilk8": ilk8,
            "ilk8_oran": 100 * ilk8 / n,
            "medyan_sira": sorted(siralar)[len(siralar) // 2] if siralar else None,
        }
    print(
        f"{ad:<26} "
        f"HEDEF ilk8 {out['hedef']['ilk8']:>4}/{out['hedef']['n']:<4} "
        f"(%{out['hedef']['ilk8_oran']:5.1f})   "
        f"KONTROL {out['kontrol']['ilk8']:>4}/{out['kontrol']['n']:<4} "
        f"(%{out['kontrol']['ilk8_oran']:5.1f})   "
        f"SUBUNIT {out['alt_kontrol']['ilk8']:>4}/{out['alt_kontrol']['n']:<4} "
        f"(%{out['alt_kontrol']['ilk8_oran']:5.1f})"
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--olustur", action="store_true", help="olcum kumesini yeniden kur")
    ap.add_argument("--hedef", type=int, default=150)
    ap.add_argument("--kontrol", type=int, default=150)
    ap.add_argument("--aday", action="append", default=[],
                    help="ad=anahtar:deger,... biciminde ek yapilandirma")
    a = ap.parse_args()

    if a.olustur or not KUME.exists():
        kume = kume_olustur(a.hedef, a.kontrol)
    else:
        kume = json.loads(KUME.read_text(encoding="utf-8"))
        print(f"kume: hedef {len(kume['hedef'])} · kontrol {len(kume['kontrol'])}")

    print()
    sonuc = {"taban": olc(kume, "taban (mevcut)")}
    sonuc["tam_sorgu"] = olc(kume, "full_query_hypothesis", full_query_hypothesis=True)

    for spec in a.aday:
        ad, _, kwspec = spec.partition("=")
        kw = {}
        for p in filter(None, kwspec.split(",")):
            k, _, v = p.partition(":")
            if v in ("True", "true"):
                kw[k] = True
            elif v.lstrip("-").isdigit():
                kw[k] = int(v)
            else:
                kw[k] = float(v)
        # Adaylar decompose'a gider, resolve'a degil.
        sonuc[ad] = olc(kume, ad, decompose_kwargs=kw)

    Path("output").mkdir(exist_ok=True)
    Path("output/decompose_olcum.json").write_text(
        json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n-> output/decompose_olcum.json")


if __name__ == "__main__":
    sys.exit(main())
