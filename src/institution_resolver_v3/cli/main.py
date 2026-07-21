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
    hybrid: bool = typer.Option(False, "--hybrid", help="BM25+kNN (RRF); embedding index gerekir"),
) -> None:
    """Tek sorgu: parent + subunit havuzlarindan top-N aday."""
    from institution_resolver_v3.elastic.search import search, search_hybrid

    finder = search_hybrid if hybrid else search
    for rt in ("parent", "subunit"):
        typer.echo(f"\n=== {rt.upper()} ({'hibrit' if hybrid else 'lexical'}) ===")
        for h in finder(query, rt, size=top):
            extra = ""
            if rt == "subunit":
                extra = f"  [{h.get('kind_label_raw')}]  parent={h.get('parent_name','')[:30]}"
            score = h.get("rrf_score", h.get("score", 0.0))
            typer.echo(f"  {score:8.4f}  {h['id']:>8}  {h['name'][:45]}{extra}")


if __name__ == "__main__":
    app()
