"""Typer uygulamasi. Komutlar fazlar ilerledikce eklenir (bkz. cli/__init__.py)."""

from __future__ import annotations

from pathlib import Path

import typer

from institution_resolver_v3 import __version__

app = typer.Typer(
    name="inres3",
    help="Institution Resolver v3 - ES aday uretimi + LLM hakem karar katmani",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Surum bilgisini yazar (iskelet dogrulamasi)."""
    typer.echo(f"institution-resolver-v3 {__version__}")


@app.command("build-data")
def build_data_cmd(
    raw_dir: Path = typer.Option(..., "--raw-dir", help="institution_parent/subunit.csv dizini"),
    out_dir: Path = typer.Option("data/processed", "--out-dir", help="JSONL + rapor cikti dizini"),
) -> None:
    """Ham CSV -> kanonik JSONL + transform_report (P1..P4, deterministik)."""
    from institution_resolver_v3.ingest.build import build_data

    report = build_data(raw_dir, out_dir)
    t = report["totals"]
    typer.echo(f"parent={t['parent']}  subunit={t['subunit']}  toplam={t['index_total']}")
    for s in report["steps"]:
        typer.echo(f"  {s['step']:26s} {s['before']:>7} -> {s['after']:>7}  (dropped {s['dropped']})")
    typer.echo(f"cikti: {out_dir}/")


@app.command("setup-es")
def setup_es_cmd() -> None:
    """ES tek-index mapping + turkish analyzer olusturur (varsa yeniden yaratir)."""
    from institution_resolver_v3.elastic.client import es_config, get_client
    from institution_resolver_v3.elastic.indexer import create_index

    client = get_client()
    index = es_config()["index"]
    create_index(client, index, recreate=True)
    typer.echo(f"index olusturuldu: {index}")


@app.command("index")
def index_cmd(
    processed_dir: Path = typer.Option("data/processed", "--processed-dir"),
    embeddings: bool = typer.Option(False, "--embeddings", help="e5 vektorlerini de uret+yukle (F3)"),
) -> None:
    """Kanonik JSONL'leri ES'e yukler + force-merge (determinizm)."""
    from institution_resolver_v3.elastic.indexer import index_data

    res = index_data(
        processed_dir / "parent_canonical.jsonl",
        processed_dir / "subunit_canonical.jsonl",
        with_embeddings=embeddings,
    )
    typer.echo(f"index={res['index']}  yuklendi={res['indexed']}  hata={len(res['errors'])}")
    typer.echo(f"  parent={res['parents']}  subunit={res['subunits']}")


@app.command("match")
def match_cmd(
    query: str = typer.Argument(..., help="serbest metin kurum ifadesi"),
    top: int = typer.Option(5, "--top", help="her havuzdan kac aday"),
) -> None:
    """Tek sorgu: decompose + parent-first cascade + sinyaller (retrieve.resolve)."""
    from institution_resolver_v3.retrieve.resolve import resolve

    result = resolve(query, size=top)
    d = result.decomposed
    typer.echo("decompose hipotezleri (secim yok, hepsi havuza katilir):")
    for i, h in enumerate(d.hypotheses or []):
        typer.echo(
            f"  H{i}: kurum={h.institution_part!r}  birim={h.unit_part!r}  "
            f"guven={h.boundary_score:.1f}  parent={h.matched_parent_name or '—'}"
        )
    if not d.hypotheses:
        typer.echo(f"  (hipotez yok)  kurum={d.institution_part!r}  guven={d.boundary_score:.1f}")

    def _cos(c) -> str:
        return f"{c.cosine:+.3f}" if c.cosine is not None else "   —  "  # None = kNN top-K'ya girmedi

    typer.echo("\n=== PARENT ===")
    for c in result.parents:
        exact = "E" if c.exact_match else " "
        typer.echo(
            f"  [{exact}] bm25={c.bm25_norm:.3f}  cos={_cos(c)}  tsr={c.token_set_ratio:5.1f}  "
            f"{c.id:>8}  {c.name[:45]}"
        )

    typer.echo("\n=== SUBUNIT ===")
    for c in result.subunits:
        flag = "P" if c.passed_parent_filter else " "
        conflict = "!" if c.qualifier_conflict else " "
        exact = "E" if c.exact_match else " "
        extra = f"  parent={c.raw.get('parent_name', '')[:25]}"
        typer.echo(
            f"  [{flag}{conflict}{exact}] bm25={c.bm25_norm:.3f}  cos={_cos(c)}  tsr={c.token_set_ratio:5.1f}  "
            f"{c.id:>8}  {c.name[:40]}{extra}"
        )


@app.command("judge")
def judge_cmd(
    query: str = typer.Argument(..., help="serbest metin kurum ifadesi"),
    model: str = typer.Option(None, "--model", help="Ollama model tag (varsayilan: config judge.model)"),
    top: int = typer.Option(5, "--top", help="her havuzdan kac aday"),
) -> None:
    """Tek sorgu: retrieve.resolve() + LLM hakem (F4, Ollama/Gemma - Claude KULLANILMIYOR)."""
    import time

    from institution_resolver_v3.config import load_config
    from institution_resolver_v3.judge.client import LlmError, OllamaClient
    from institution_resolver_v3.judge.judge import JudgeValidationError, judge as run_judge
    from institution_resolver_v3.retrieve.resolve import resolve

    cfg = load_config()["judge"]
    client = OllamaClient(model=model or cfg["model"], host=cfg["host"])

    t0 = time.time()
    result = resolve(query, size=top)
    t1 = time.time()
    try:
        verdict = run_judge(result, client)
    except (JudgeValidationError, LlmError) as exc:
        typer.echo(f"HAKEM HATASI: {exc}", err=True)
        raise typer.Exit(code=1) from None
    t2 = time.time()

    def _candidate_of(matched_id: str | None, pool):
        if matched_id is None:
            return None
        return next((c for c in pool if c.id == matched_id), None)

    p_cand = _candidate_of(verdict.parent.matched_id, result.parents)
    p_name = p_cand.name if p_cand else ""
    typer.echo(f"parent   : {verdict.parent.verdict:12s} {p_name:35s} id={verdict.parent.matched_id or '—'}")
    if verdict.subunit is not None:
        s_cand = _candidate_of(verdict.subunit.matched_id, result.subunits)
        s_name = s_cand.name if s_cand else ""
        s_parent = f" ({s_cand.raw.get('parent_name')})" if s_cand and s_cand.raw.get("parent_name") else ""
        s_display = f"{s_name}{s_parent}"
        typer.echo(
            f"subunit  : {verdict.subunit.verdict:12s} {s_display:45s} id={verdict.subunit.matched_id or '—'}"
        )
    else:
        typer.echo("subunit  : (sorguda istenmedi)")
    typer.echo(
        f"\n[süre]     resolve={t1 - t0:.2f}s  llm={t2 - t1:.2f}s  toplam={t2 - t0:.2f}s"
        "  (not: embedding modeli her CLI cagrisinda ayrica yuklenir, bu 'toplam'a girmez)"
    )


@app.command("batch")
def batch_cmd(
    input_csv: str = typer.Argument(..., help="girdi CSV yolu"),
    query_col: str = typer.Option("raw_name", "--query-col", help="sorgu metnini tasiyan kolon"),
    out: str = typer.Option("batch_sonuc.csv", "--out", help="sonuc CSV yolu"),
    limit: int = typer.Option(None, "--limit", help="en fazla bu kadar girdi isle"),
    resume: bool = typer.Option(False, "--resume", help="cikti varsa kaldigi yerden devam"),
    model: str = typer.Option(None, "--model", help="Ollama model tag (varsayilan: config judge.model)"),
    top: int = typer.Option(5, "--top", help="her havuzdan kac aday"),
) -> None:
    """F5 batch: bir CSV'deki kurum ifadelerini resolve+hakem'den gecirip sonuc
    CSV'sine yazar (no_match/review/ambiguous ve hatalar dahil - bkz. eval/batch.py)."""
    import csv as _csv

    from institution_resolver_v3.config import load_config
    from institution_resolver_v3.eval.batch import run_batch
    from institution_resolver_v3.judge.client import OllamaClient

    src = Path(input_csv)
    if not src.exists():
        typer.echo(f"Girdi CSV bulunamadi: {src}", err=True)
        raise typer.Exit(code=1)

    with src.open(newline="", encoding="utf-8") as f:
        header = next(_csv.reader(f), [])
    if query_col not in header:
        typer.echo(f"'{query_col}' kolonu CSV'de yok. Mevcut kolonlar: {header}", err=True)
        raise typer.Exit(code=1)

    cfg = load_config()["judge"]
    client = OllamaClient(model=model or cfg["model"], host=cfg["host"])

    def _queries():
        with src.open(newline="", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                q = (row.get(query_col) or "").strip()
                if q:
                    yield q

    def _progress(i: int, query: str, rec: dict) -> None:
        if rec["status"] == "error":
            tail = f"HATA: {rec['error'][:60]}"
        else:
            sub = rec["subunit_verdict"] or "-"
            tail = f"{rec['parent_verdict']}/{rec['parent_id'] or '-'} | subunit={sub}"
        typer.echo(f"[{i}] {query[:50]!r:<54} -> {tail}", err=True)

    typer.echo(f"Batch basliyor: {src}  (kolon='{query_col}', model={model or cfg['model']}) -> {out}", err=True)
    summary = run_batch(
        _queries(), client, out, limit=limit, resume=resume, top=top, on_progress=_progress
    )
    typer.echo(
        f"\nBITTI: ok={summary['ok']}  hata={summary['error']}  atlandi={summary['skipped']}"
        f"  -> {summary['out']}"
    )


if __name__ == "__main__":
    app()
