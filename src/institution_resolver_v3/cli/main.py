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


if __name__ == "__main__":
    app()
