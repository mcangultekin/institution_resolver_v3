"""V4E'nin `auto_match` dediklerinden 30 satirlik nokta kontrolu.

NEDEN (2026-08-15): 143 bin satirlik uretim kosusu, YALNIZCA elle verilmis
doğru/yanlis yargilarina dayanan bir yapilandirmayla baslatilacak. Gold seti
kullanici karariyla reddedildi; bu onun yerine gecmez ve gecmeye calismaz -
tek soruyu cevaplar: **`auto_match` dediklerinin kaci gercekten dogru?**
O sayi `config/default.yaml`'daki `decision.auto_precision_target: 0.98`
hedefinin bugune kadar hic olculmemis karsiligidir.

Karar esikleri (kosudan ONCE belirlendi, sonradan kaydirilmasin):
    >= %95  -> yapilandirma yeterli, uretim kosusu baslatilabilir
    ~ %85   -> daha siki kapi (V4EC) tartisilmali, 5 puan daha auto kaybi
    <= %75  -> hicbir prompt/sema ayari yetmiyor, retrieval'a donulmeli

Ornekleme: `auto_match` satirlarindan sha256 tabanli, surumden bagimsiz secim
(scripts/build_faz0_sample.py ile ayni desen) - tekrar kosulunca ayni 30 satir.

Kullanim:
    python3 scripts/spot_check.py --olustur     # dosyayi uret
    python3 scripts/spot_check.py               # etiketle (resume'lu)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

csv.field_size_limit(10_000_000)

KOSU = Path("output/ab_v4e_local.csv")
CIKTI = Path("data/eval/spot_check_v4e.csv")
SEED = "20260815"
N = 30

ALANLAR = ["sira", "query", "secilen_id", "secilen_ad", "ulke", "sehir",
           "havuz", "dogru", "not"]
CEVAP = {"e": "1", "h": "0", "p": "?"}


class _Cik(Exception):
    """'q' ile istekli cikis."""


def olustur() -> None:
    with KOSU.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["variant"] == "V4E" and r["status"] == "ok"
                and r["parent_verdict"] == "auto_match"]
    print(f"V4E auto_match havuzu: {len(rows)} satir")
    secim = sorted(rows, key=lambda r: hashlib.sha256(
        f"{SEED}|{r['query']}".encode()).hexdigest())[:N]

    out = []
    for i, r in enumerate(sorted(secim, key=lambda r: r["query"]), start=1):
        pool = [c for c in json.loads(r["candidates_json"]) if c["kind"] == "parent"]
        secilen = next((c for c in pool if c["id"] == r["parent_id"]), None)
        # Havuzun tamami gosterilir: "dogru cevap zaten listede yoktu" ile
        # "listedeydi ama yanlisi secildi" ayrimi ancak boyle yapilabilir.
        havuz = " | ".join(
            f"{c['name'][:38]}({c.get('country') or '?'})" for c in pool if c["id"] != r["parent_id"]
        )
        out.append({
            "sira": i, "query": r["query"],
            "secilen_id": r["parent_id"], "secilen_ad": r["parent_name"],
            "ulke": (secilen or {}).get("country") or "?",
            "sehir": (secilen or {}).get("city") or "?",
            "havuz": havuz, "dogru": "", "not": "",
        })
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    with CIKTI.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ALANLAR)
        w.writeheader()
        w.writerows(out)
    muhur = hashlib.sha256("\n".join(sorted(r["query"] for r in out)).encode()).hexdigest()[:16]
    print(f"{len(out)} satir -> {CIKTI}\nMUHUR: {muhur}")


def _sor(prompt: str) -> str:
    while True:
        v = input(prompt).strip().lower()
        if v == "q":
            raise _Cik()
        if v in CEVAP:
            return CEVAP[v]
        print("  gecersiz - e/h/p/q")


def etiketle() -> None:
    if not CIKTI.exists():
        sys.exit(f"once uret: python3 {sys.argv[0]} --olustur")
    with CIKTI.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    kalan = [r for r in rows if not r["dogru"]]
    if not kalan:
        _ozet(rows)
        return
    print(f"{len(rows)} satirdan {len(kalan)} tanesi bos.")
    print("e=dogru  h=yanlis  p=emin degilim  q=cik (ilerleme kaydedilir)\n")
    try:
        for i, r in enumerate(kalan, start=1):
            print(f"[{i}/{len(kalan)}]  {r['query']}")
            print(f"    SECILEN : {r['secilen_ad']}  ({r['ulke']}/{r['sehir']})")
            print(f"    havuzdaki digerleri: {r['havuz'][:150] or '(yok)'}")
            r["dogru"] = _sor("    dogru mu? (e/h/p/q): ")
            with CIKTI.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=ALANLAR)
                w.writeheader()
                w.writerows(rows)   # her cevaptan sonra diske - cokme guvenli
            print()
    except (KeyboardInterrupt, EOFError, _Cik):
        print("\n\nDurduruldu, cevaplar kaydedildi. Tekrar calistir, kaldigi yerden devam eder.")
        return
    _ozet(rows)


def _ozet(rows: list[dict]) -> None:
    d = sum(1 for r in rows if r["dogru"] == "1")
    y = sum(1 for r in rows if r["dogru"] == "0")
    b = sum(1 for r in rows if r["dogru"] == "?")
    kesin = d + y
    print("\n" + "=" * 52)
    print(f"dogru {d}  yanlis {y}  emin degil {b}")
    if kesin:
        p = 100 * d / kesin
        print(f"auto_match KESINLIGI: %{p:.0f}   ({d}/{kesin})")
        print("-" * 52)
        if p >= 95:
            print("=> yapilandirma yeterli, uretim kosusu baslatilabilir")
        elif p >= 85:
            print("=> siniri asmiyor; daha siki kapi (V4EC) tartisilmali")
        else:
            print("=> prompt/sema ayari yetmiyor, retrieval'a donulmeli")
    print(f"\nhedef (config decision.auto_precision_target): %98")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--olustur", action="store_true")
    a = ap.parse_args()
    olustur() if a.olustur else etiketle()
