"""coverage_weight uctan uca A/B - gate + HAKEM dahil.

NEDEN (2026-08-17): decompose duzeltmesinin tum olcumleri HAVUZ seviyesinde
yapildi (LLM'siz). Hakem katmani hic olculmedi. Havuz olcumu gosterdi ki
"katalogda kesin karsiligi yok" sorgularinin %35'inde ilk-8 havuzu tamamen
degisiyor (ortak aday ort. 1,3/8) - yani hakem bir ucte birlik kesimde YENI
adaylar goruyor ve "eminim ki yanlis" uretip uretmedigi bilinmiyor.

UC POPULASYON, her biri farkli bir soruyu cevaplar:
  risk     : katalogda karsiligi YOK (ayirt edici tokeni katalogda hic gecmiyor)
             -> duzeltme uydurma eslesme yaratiyor mu?
  kurtarma : su an yanlis no_match, dogru cevap katalogda apacik
             -> duzeltme gercekten kurtariyor mu?
  koruma   : su an auto_match
             -> duzeltme calisani boziyor mu?

IKI KOL ART ARDA, AYNI SUREC: hakem ayni ortamda bayt-denk ama ortam
degisince kayiyor (olculdu; 5-6 Agustos kosulari arasinda %9,3 karar farki
ortam kaynakliydi). Farkli oturumlarin CSV'leri KIYASLANAMAZ.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import time
from pathlib import Path

from institution_resolver_v3.jobs.inventory import FIELDNAMES, process_one_inventory
from institution_resolver_v3.judge.client import OllamaClient
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
CIKTI = Path("output")


def _tok(s: str) -> list[str]:
    return normalize(s).base_no_accent.split()


def kumeler(n_grup: int) -> dict[str, list[str]]:
    df = load_token_df()
    katalog_tok: set[str] = set()
    ters: dict[str, set[str]] = collections.defaultdict(set)
    with KATALOG.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            metin = [r.get("name") or ""] + [
                a.get("value", "") for a in (r.get("aliases") or [])
            ]
            gorulen = {x for m in metin for x in _tok(m)}
            katalog_tok |= gorulen
            for t in gorulen:
                if df.get(t, 0) <= DEFAULT_MAX_DF and len(t) >= DEFAULT_MIN_LEN:
                    ters[t].add(r["id"])

    risk, kurtarma, koruma = [], [], []
    with KOSU.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            v, q = r["parent_verdict"], r["query"]
            if v == "auto_match" and r["parent_id"]:
                koruma.append(q)
                continue
            if v != "no_match":
                continue
            ayirt = [t for t in dict.fromkeys(_tok(q))
                     if len(t) >= DEFAULT_MIN_LEN and df.get(t, 0) <= DEFAULT_MAX_DF]
            if not ayirt:
                continue
            if not any(t in katalog_tok for t in ayirt):
                risk.append(q)
            elif len(ayirt) >= 2:
                say: collections.Counter[str] = collections.Counter()
                for t in ayirt:
                    for pid in ters.get(t, ()):
                        say[pid] += 1
                if say and say.most_common(1)[0][1] == len(ayirt):
                    kurtarma.append(q)

    k = lambda q: hashlib.sha256(q.encode()).hexdigest()  # noqa: E731
    out = {
        "risk": sorted(risk, key=k)[:n_grup],
        "kurtarma": sorted(kurtarma, key=k)[:n_grup],
        "koruma": sorted(koruma, key=k)[:n_grup],
    }
    for ad, v in out.items():
        print(f"  {ad:<9} {len(v)} sorgu")
    return out


# Kosu ~1 saat surdugu icin ilerleme YAZDIRILIR: iki kolun toplam is
# sayisi uzerinden %20'lik adimlarda tek satir. Monitor bu satirlari
# olaya cevirir; kol sonlarini beklemek %50 cozunurluk demekti.
_ILERLEME = {"yapilan": 0, "toplam": 0, "sonraki": 20}
_BASLANGIC = [0.0]


def kol(kume: dict[str, list[str]], ad: str, client, token_df, w: float | None) -> dict:
    kw = {"decompose_kwargs": {"coverage_weight": w}} if w else {}
    rfn = lambda q, **ek: resolve(q, **{**ek, **kw})  # noqa: E731
    kayitlar = {}
    t0 = time.time()
    for grup, sorgular in kume.items():
        for q in sorgular:
            kayitlar[(grup, q)] = process_one_inventory(
                q, client=client, resolve_fn=rfn, token_df=token_df)
            _ILERLEME["yapilan"] += 1
            yuzde = 100 * _ILERLEME["yapilan"] / max(_ILERLEME["toplam"], 1)
            if yuzde >= _ILERLEME["sonraki"]:
                gecen = (time.time() - _BASLANGIC[0]) / 60
                kalan = gecen * (100 - yuzde) / max(yuzde, 1)
                print(f"ILERLEME %{_ILERLEME['sonraki']}  "
                      f"({_ILERLEME['yapilan']}/{_ILERLEME['toplam']})  "
                      f"gecen {gecen:.0f} dk  kalan ~{kalan:.0f} dk", flush=True)
                _ILERLEME["sonraki"] += 20
    print(f"  {ad}: {len(kayitlar)} sorgu, {(time.time()-t0)/60:.1f} dk")
    return kayitlar


def _ozet(kayitlar: dict, grup: str) -> dict:
    r = [v for (g, _), v in kayitlar.items() if g == grup]
    n = len(r) or 1
    return {
        "n": len(r),
        "auto_match": sum(1 for x in r if x["parent_verdict"] == "auto_match"),
        "review": sum(1 for x in r if x["parent_verdict"] == "review"),
        "no_match": sum(1 for x in r if x["parent_verdict"] == "no_match"),
        "hata": sum(1 for x in r if x["status"] != "ok"),
        "kapi": sum(1 for x in r if x["gate_orphan_fired"] == "1"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100, help="grup basina sorgu")
    ap.add_argument("--w", type=float, default=0.25)
    ap.add_argument("--model", default="gemma4:e4b")
    a = ap.parse_args()

    print("Kumeler kuruluyor...")
    kume = kumeler(a.n)
    token_df = load_token_df()
    client = OllamaClient(model=a.model)
    CIKTI.mkdir(exist_ok=True)

    _ILERLEME["toplam"] = 2 * sum(len(v) for v in kume.values())
    _BASLANGIC[0] = time.time()
    print(f"\nIKI KOL ART ARDA (ayni surec, ayni ortam) - {_ILERLEME['toplam']} cagri:")
    A = kol(kume, "A taban    ", client, token_df, None)
    B = kol(kume, f"B w={a.w}  ", client, token_df, a.w)

    print(f"\n{'grup':<10}{'kol':<8}{'auto':>6}{'review':>8}{'no_match':>10}{'hata':>7}{'kapi':>7}")
    print("-" * 56)
    for grup in ("risk", "kurtarma", "koruma"):
        for ad, k in (("taban", A), (f"w{a.w}", B)):
            s = _ozet(k, grup)
            print(f"{grup if ad == 'taban' else '':<10}{ad:<8}"
                  f"{s['auto_match']:>6}{s['review']:>8}{s['no_match']:>10}"
                  f"{s['hata']:>7}{s['kapi']:>7}")
        print()

    # Kararı degisen satirlar - elle inceleme icin diske
    degisen = []
    for anahtar in A:
        a_, b_ = A[anahtar], B[anahtar]
        if (a_["parent_verdict"], a_["parent_id"]) != (b_["parent_verdict"], b_["parent_id"]):
            degisen.append({
                "grup": anahtar[0], "query": anahtar[1],
                "taban_verdict": a_["parent_verdict"], "taban_ad": a_["parent_name"],
                "yeni_verdict": b_["parent_verdict"], "yeni_ad": b_["parent_name"],
                "taban_hata": a_["error"][:60], "yeni_hata": b_["error"][:60],
            })
    p = CIKTI / "ab_coverage_degisenler.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=list(degisen[0]) if degisen else ["grup"])
        w_.writeheader()
        w_.writerows(degisen)
    print(f"karari degisen: {len(degisen)}/{len(A)}  -> {p}")
    for d in degisen[:10]:
        print(f"  [{d['grup']:<8}] {d['query'][:38]:<40} "
              f"{d['taban_verdict']:<10} -> {d['yeni_verdict']:<10} {d['yeni_ad'][:26]}")


if __name__ == "__main__":
    main()
