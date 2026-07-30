"""run_csv_batch testleri - 3 batch turunun (llm/gate/hibrit) ortak CSV
yazim/resume/limit iskeleti. Once bu dosya yoktu (csv_runner.py testsiz,
bkz. 00_OZET.md T4) - burada belgelenen iki hata (DURUM/00_OZET'te
kanitlanmis) kirmizi testle sabitleniyor, sonra duzeltiliyor."""

from __future__ import annotations

import csv

from institution_resolver_v3.eval.csv_runner import run_csv_batch

FIELDNAMES = ["query", "status", "value"]


def _process_one(query: str) -> dict[str, str]:
    return {"query": query, "status": "ok", "value": query.upper()}


def _write_existing(path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _read_rows(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_resume_with_limit_makes_progress(tmp_path):
    """Onceki kosu 2 sorguyu bitirmis; --resume --limit=2 ile devam edince
    limit ZATEN-YAPILMIS satirlari degil, bu cagirida YAZILAN yeni satir
    sayisini saymali. Eski davranis: limit input-sirasini sayiyordu, ilk 2
    sorgu zaten 'done' oldugundan hicbir yeni satir yazilmadan break ediyordu
    (bkz. 00_OZET T4: '--limit N --resume hic ilerlemiyor')."""
    out = tmp_path / "res.csv"
    _write_existing(out, [
        {"query": "a", "status": "ok", "value": "A"},
        {"query": "b", "status": "ok", "value": "B"},
    ])

    summary = run_csv_batch(
        ["a", "b", "c", "d", "e"], out, FIELDNAMES, _process_one, limit=2, resume=True
    )

    assert summary["ok"] == 2, "limit=2 ile 2 YENI satir yazilmali (c, d)"
    rows = _read_rows(out)
    assert [r["query"] for r in rows] == ["a", "b", "c", "d"]


def test_resume_preserves_duplicate_queries(tmp_path):
    """Girdide ayni sorgu metni iki kez geciyorsa (mesru - CSV'de tekil
    olmasi garanti degil), yarim kalmis bir kosudan resume edince HER iki
    tekrar da ayri satir olarak korunmali. Eski davranis: 'done' duz bir
    set(str) oldugundan tek 'X' kaydi, sonraki TUM 'X' tekrarlarini yutuyordu
    (bkz. 00_OZET T4: 'tekrarli sorgular sessizce dusuyor, 3 satir vs 2 satir')."""
    out = tmp_path / "res.csv"
    _write_existing(out, [{"query": "X", "status": "ok", "value": "X"}])

    summary = run_csv_batch(["X", "X", "Y"], out, FIELDNAMES, _process_one, resume=True)

    assert summary["ok"] == 2, "ikinci 'X' tekrari ve 'Y' yeni satir olarak islenmeli"
    rows = _read_rows(out)
    assert [r["query"] for r in rows] == ["X", "X", "Y"]


def test_resume_rejects_header_mismatch(tmp_path):
    """Cikti dosyasinin basligi cagrilan fieldnames ile uyusmuyorsa (ör.
    eski semali bir dosyaya yeni kolonlarla resume edilmeye calisiliyor),
    sessizce kolon kaymasi yerine acik hata verilmeli."""
    out = tmp_path / "res.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "status"])  # 'value' eksik
        writer.writeheader()
        writer.writerow({"query": "a", "status": "ok"})

    try:
        run_csv_batch(["a", "b"], out, FIELDNAMES, _process_one, resume=True)
        assert False, "baslik uyusmazliginda hata beklenirdi"
    except ValueError as exc:
        assert "uyusmuyor" in str(exc).lower() or "header" in str(exc).lower()
