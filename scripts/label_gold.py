"""Terminalden gold etiketleme: gold_kuyruk CSV'sini satir satir gezip
e/h/p (evet/hayir/pas) ile YALNIZ gold_dogru (parent) doldurur.
`gold_subunit_dogru` bilerek SORULMUYOR (kullanici karari) - kolon bos
kalir, ayri bir oturumda/araci ile sonra doldurulabilir.

Ilerleme her cevaptan sonra diske yazilir (cokme-guvenli) - script yarida
kesilirse (Ctrl+C, q, terminal kapanmasi) tekrar calistirinca KALDIGI
YERDEN devam eder: dolu (bos olmayan) hucreler tekrar sorulmaz. 'pas' ->
'?' olarak kaydedilir, o da bir sonraki kosuda tekrar SORULMAZ (bilerek
atlandi sayilir; '?' satirlarini tekrar gormek icin hucreyi elle silmek
gerekir).

Kullanim:
    python3 scripts/label_gold.py                                  # varsayilan dosya
    python3 scripts/label_gold.py data/eval/gold_kuyruk_2026-07-30.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

DEFAULT_PATH = "data/eval/gold_kuyruk_2026-07-30.csv"

ANSWER_MAP = {"e": "1", "h": "0", "p": "?"}


class _Quit(Exception):
    """'q' ile istekli cikis - KeyboardInterrupt/EOFError'la ayni sekilde yakalanir."""


def _ask(prompt: str) -> str:
    while True:
        raw = input(prompt).strip().lower()
        if raw == "q":
            raise _Quit()
        if raw in ANSWER_MAP:
            return ANSWER_MAP[raw]
        print("  gecersiz - e/h/p/q gir")


def _save(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH)
    if not path.exists():
        print(f"dosya yok: {path}", file=sys.stderr)
        raise SystemExit(1)

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    total = len(rows)
    pending = [r for r in rows if not r.get("gold_dogru")]
    if not pending:
        print(f"Hepsi etiketlenmis ({total} satir). Yapilacak bir sey yok.")
        return

    print(f"{total} satirdan {len(pending)} tanesi eksik. e=evet h=hayir p=pas q=cik  (Ctrl+C de ayni islevi gorur)\n")

    try:
        for i, row in enumerate(pending, start=1):
            print(f"[{i}/{len(pending)}]")
            print(f"  sorgu     : {row['query']}")
            print(f"  parent    : {row['parent_name']}  (id={row['parent_id']})")

            row["gold_dogru"] = _ask("  parent dogru mu? (e/h/p/q): ")
            _save(path, fieldnames, rows)

            print()
    except (KeyboardInterrupt, EOFError, _Quit):
        print("\n\nDurduruldu - su ana kadarki cevaplar kaydedildi. Devam etmek icin scripti tekrar calistir.")
        return

    print("Hepsi etiketlendi.")


if __name__ == "__main__":
    main()
