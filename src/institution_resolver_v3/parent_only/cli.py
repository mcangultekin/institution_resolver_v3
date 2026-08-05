"""`inres3-parent` CLI - parent-only mod (bkz. pyproject.toml [project.scripts]).

Mevcut `inres3` komutundan AYRI bir giris noktasidir: iki uygulama birbirini
import etmez, bu yuzden burada bir hata olsa bile `inres3` etkilenmez
(kullanici karari 2026-08-04, secenek "b").

Agir importlar (ES, embedding, Ollama) komut govdelerinin ICINDE yapilir -
`--help` ve hatali kullanim ES/model yuklemeden aninda donsun diye (cekirdek
cli/main.py ile ayni desen)."""

from __future__ import annotations

import csv as _csv
from pathlib import Path

import typer

from institution_resolver_v3 import __version__

app = typer.Typer(
    name="inres3-parent",
    help="Institution Resolver v3 - parent-only mod (yalniz kurum; subunit aranmaz)",
    no_args_is_help=True,
)


def _read_queries(src: Path, query_col: str):
    with src.open(newline="", encoding="utf-8") as fh:
        for row in _csv.DictReader(fh):
            q = (row.get(query_col) or "").strip()
            if q:
                yield q


def _check_csv(input_csv: str, query_col: str) -> Path:
    src = Path(input_csv)
    if not src.exists():
        typer.echo(f"Girdi CSV bulunamadi: {src}", err=True)
        raise typer.Exit(code=1)
    with src.open(newline="", encoding="utf-8") as f:
        header = next(_csv.reader(f), [])
    if query_col not in header:
        typer.echo(f"'{query_col}' kolonu CSV'de yok. Mevcut kolonlar: {header}", err=True)
        raise typer.Exit(code=1)
    return src


@app.command()
def version() -> None:
    """Surum bilgisi."""
    typer.echo(f"institution-resolver-v3 parent-only {__version__}")


@app.command("match")
def match_cmd(
    query: str = typer.Argument(..., help="serbest metin kurum ifadesi"),
    top: int = typer.Option(5, "--top", help="kac parent adayi"),
    max_span: int = typer.Option(None, "--max-span", help="decompose pencere siniri (varsayilan: sinirsiz)"),
) -> None:
    """Aday havuzunu ve ham sinyalleri gosterir (karar YOK)."""
    import time

    from institution_resolver_v3.parent_only.resolve import resolve_parent

    t0 = time.time()
    res = resolve_parent(query, size=top, max_span=max_span)
    dt = time.time() - t0

    d = res.decomposed
    typer.echo(f"decompose: kurum={d.institution_part!r}  (skor {d.boundary_score:.1f})")
    typer.echo(f"\n{'id':>8}  {'tsr':>5}  {'bm25':>5}  {'exact':>5}  ad")
    for c in res.parents:
        ex = "EVET" if c.exact_match else "-"
        typer.echo(f"{c.id:>8}  {c.token_set_ratio:>5.1f}  {c.bm25_norm:>5.2f}  {ex:>5}  {c.name[:60]}")
    typer.echo(f"\n{len(res.parents)} aday  [süre {dt:.2f}s]")


@app.command("gate")
def gate_cmd(
    query: str = typer.Argument(..., help="serbest metin kurum ifadesi"),
    top: int = typer.Option(5, "--top", help="kac parent adayi"),
    max_span: int = typer.Option(None, "--max-span", help="decompose pencere siniri"),
) -> None:
    """Deterministik triyaj (LLM YOK)."""
    import time

    from institution_resolver_v3.parent_only.gate import gate_parent
    from institution_resolver_v3.parent_only.genericity import es_containment_counts
    from institution_resolver_v3.parent_only.resolve import resolve_parent

    t0 = time.time()
    res = resolve_parent(query, size=top, max_span=max_span)
    # jenerik-ad korumasi icin ad sayilari (tek msearch) - decide yolundaki ile ayni
    counts = es_containment_counts([c.name for c in res.parents]) if res.parents else {}
    g = gate_parent(res, name_counts=counts)
    dt = time.time() - t0

    name = next((c.name for c in res.parents if c.id == g.matched_id), "")
    typer.echo(f"parent : {g.verdict:12s} {name[:45]:45s} id={g.matched_id or '—'}")
    typer.echo(f"guven  : {g.confidence:.3f}   sinyaller: {g.signals}")
    typer.echo(f"[süre {dt:.2f}s]")


@app.command("decide")
def decide_cmd(
    query: str = typer.Argument(..., help="serbest metin kurum ifadesi"),
    mode: str = typer.Option("hybrid", "--mode", help="gate | hybrid | llm"),
    model: str = typer.Option(None, "--model", help="Ollama model tag (varsayilan: config judge.model)"),
    top: int = typer.Option(5, "--top", help="kac parent adayi"),
    max_span: int = typer.Option(None, "--max-span", help="decompose pencere siniri"),
) -> None:
    """Nihai kurum karari. mode=gate: LLM yok · hybrid: gate auto vermezse hakem ·
    llm: her sorgu hakeme."""
    import time

    from institution_resolver_v3.config import load_config
    from institution_resolver_v3.judge.client import LlmError, OllamaClient
    from institution_resolver_v3.judge.judge import JudgeValidationError
    from institution_resolver_v3.parent_only.decide import MODES, decide_parent

    if mode not in MODES:
        typer.echo(f"Gecersiz --mode={mode!r}. Beklenen: {', '.join(MODES)}", err=True)
        raise typer.Exit(code=1)

    client = None
    if mode != "gate":
        cfg = load_config()["judge"]
        client = OllamaClient(model=model or cfg["model"], host=cfg["host"])

    t0 = time.time()
    try:
        d = decide_parent(query, client, mode=mode, size=top, max_span=max_span)
    except (JudgeValidationError, LlmError) as exc:
        typer.echo(f"HAKEM HATASI: {exc}", err=True)
        debug = getattr(exc, "debug", None)
        if debug:
            typer.echo(f"  detay: {debug}", err=True)
        raise typer.Exit(code=1) from None
    dt = time.time() - t0

    typer.echo(
        f"parent : {d.verdict:12s} {d.matched_name[:45]:45s} id={d.matched_id or '—'}  [{d.decided_by}]"
    )
    if d.decided_by == "judge":
        typer.echo(f"  (gate ne demisti: {d.gate.verdict}, {d.gate.signals.get('reason', '')})")
    typer.echo(f"\nmod={mode}  karar kaynagi={d.decided_by}  [süre {dt:.2f}s]")


@app.command("batch")
def batch_cmd(
    input_csv: str = typer.Argument(..., help="girdi CSV yolu"),
    query_col: str = typer.Option("raw_name", "--query-col", help="sorgu metnini tasiyan kolon"),
    out: str = typer.Option("parent_batch_sonuc.csv", "--out", help="sonuc CSV yolu"),
    mode: str = typer.Option("hybrid", "--mode", help="gate | hybrid | llm"),
    limit: int = typer.Option(None, "--limit", help="en fazla bu kadar YENI satir isle"),
    resume: bool = typer.Option(False, "--resume", help="cikti varsa kaldigi yerden devam"),
    model: str = typer.Option(None, "--model", help="Ollama model tag (varsayilan: config judge.model)"),
    top: int = typer.Option(5, "--top", help="kac parent adayi"),
    max_span: int = typer.Option(None, "--max-span", help="decompose pencere siniri"),
    workers: int = typer.Option(1, "--workers", help="es-zamanli isci sayisi (IO-bound; varsayilan sirali)"),
) -> None:
    """CSV in -> CSV out. mode=gate LLM'siz ve en hizlisidir."""
    from institution_resolver_v3.config import load_config
    from institution_resolver_v3.parent_only.batch import run_parent_batch
    from institution_resolver_v3.parent_only.decide import MODES

    if mode not in MODES:
        typer.echo(f"Gecersiz --mode={mode!r}. Beklenen: {', '.join(MODES)}", err=True)
        raise typer.Exit(code=1)

    src = _check_csv(input_csv, query_col)

    client = None
    model_name = "-"
    if mode != "gate":
        from institution_resolver_v3.judge.client import OllamaClient

        cfg = load_config()["judge"]
        model_name = model or cfg["model"]
        client = OllamaClient(model=model_name, host=cfg["host"])

    def _progress(i: int, query: str, rec: dict) -> None:
        if rec["status"] == "error":
            tail = f"HATA: {rec['error'][:60]}"
        else:
            tail = f"[{rec['decided_by']}] {rec['verdict']}/{rec['parent_id'] or '-'}"
        typer.echo(f"[{i}] {query[:50]!r:<54} -> {tail}", err=True)

    typer.echo(
        f"Parent-batch basliyor: {src}  (kolon='{query_col}', mod={mode}, model={model_name}) -> {out}",
        err=True,
    )
    summary = run_parent_batch(
        _read_queries(src, query_col),
        out,
        client=client,
        mode=mode,
        top=top,
        max_span=max_span,
        limit=limit,
        resume=resume,
        on_progress=_progress,
        max_workers=workers,
    )
    typer.echo(
        f"\nBITTI: ok={summary['ok']}  hata={summary['error']}  atlandi={summary['skipped']}"
        f"  -> {summary['out']}"
    )


if __name__ == "__main__":  # `python -m institution_resolver_v3.parent_only.cli`
    app()
