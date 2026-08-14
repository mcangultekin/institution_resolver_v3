"""Hakem A/B tezgahi - ayni sorgulara, AYNI HAVUZLA, tek oturumda N varyant.

Neden var (bkz. docs/RAPOR_2026-08-14_llm_katmani_deneyleri.md):
onceki oturumun 700 cagrilik deney kodu silindigi icin hicbir sayi
tekrarlanamiyor; ayrica uretim CSV'lerinde ne prompt hash'i ne ham LLM yaniti
ne de aday havuzu var - 314 hatanin kok nedeni `resolve()` yeniden kosulmadan
gorulemiyor. Bu script ikisini birden kapatir.

IKI TASARIM KARARI (olcumun temizligi icin):

1. `resolve()` sorgu basina BIR KEZ kosar, aday havuzu TUM varyantlara aynen
   verilir. Hem ~%50 hizli (resolve ort. 0,65 sn) hem de daha onemlisi:
   varyantlar arasinda YALNIZ prompt/sema degisir, havuz fiziksel olarak ayni
   kalir - "acaba havuz mu farkliydi" sorusu ortadan kalkar.

2. FARKLI varyantlar sorgu basina arka arkaya kosar (v1,v3 -> sonraki sorgu),
   tum v1'ler sonra tum v3'ler DEGIL. Model isindikca/GPU durumu degistikce
   olusan zaman kaymasi boylece varyantlara esit dagilir; yoksa "v3 daha iyi"
   dedigimiz sey "v3 daha gec kosuldu" olabilirdi.

3. TEKRARLAR (ayni varyantin 2. kez yazilmasi, `--variants v1,v1,v3`) AYRI BIR
   GECISTE kosar - pes pese DEGIL. Nedeni canli olculdu (2026-08-14, 3 sorgu):
   ayni prompt hemen tekrar sorulunca Ollama KV-cache'i yeniden kullaniyor
   (21,97 sn -> 2,03 sn) ve ayni durumdan devam ettigi icin cikti YAPAY OLARAK
   birebir ayni cikiyor. Pes pese tekrar bagimsiz bir ornek DEGILDIR; gurultu
   tabanini sifir gosterirdi. Ayri gecis, arada 100+ baska prompt gectigi icin
   onbellegi dusurur ve tekrar gercekten bagimsiz olur.

Boylece `--variants v1,v1,v3` iki gecis kosar:
    gecis 0:  her sorgu icin v1#0, v3#0   (varyant karsilastirmasi)
    gecis 1:  her sorgu icin v1#1         (gurultu tabani)

UYARI - SURE KARSILASTIRMASI: `judge_s` varyantlar arasi DOGRUDAN
karsilastirilamaz. Prompt'lar ortak bir onek paylastigi icin ayni sorguda ikinci
varyant kismi onbellekten yararlanir. Hiz iddiasi (ör. "v3 daha kisa, daha
hizli") ancak varyant sirasi degistirilerek ya da ayri bir olcumle kurulabilir;
KARARLAR bundan etkilenmez.

Kullanim:
    python3 scripts/judge_ab.py run  --variants v1,v1,v3 --out output/ab_1.csv
    python3 scripts/judge_ab.py diff --run output/ab_1.csv --a v1#0 --b v1#1
    python3 scripts/judge_ab.py diff --run output/ab_1.csv --a v1#0 --b kaggle
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from institution_resolver_v3.judge.candidates import build_candidate_views  # noqa: E402
from institution_resolver_v3.judge.client import LlmError, OllamaClient  # noqa: E402
from institution_resolver_v3.judge.judge import JudgeValidationError  # noqa: E402
from institution_resolver_v3.judge.judge import judge as _judge  # noqa: E402
from institution_resolver_v3.judge.variants import get_variant  # noqa: E402
from institution_resolver_v3.retrieve.resolve import resolve as _resolve  # noqa: E402

csv.field_size_limit(10_000_000)

DEFAULT_SAMPLE = "data/eval/faz0_ornek_125.csv"

# --- KOLLAR -----------------------------------------------------------------
# Bir "kol" = prompt varyanti + RETRIEVAL/GORUNUM ayari. Prompt varyantlari tek
# basina yetmiyor cunku 2026-08-14 olcumu felaket vakalarin sebebinin prompt
# degil HAVUZ SIRASI/GORUNUMU oldugunu gosterdi (dogru kayit havuzun 8. ve 10.
# sirasindaydi, kirpma 8'de kesiyordu).
#
# `--variants` hem kol adi hem duz prompt varyanti kabul eder: kol adi verilirse
# o kolun tum ayarlari uygulanir, degilse prompt varyanti + varsayilan ayarlar.
ARMS: dict[str, dict] = {
    # A: bugunku uretim - taban
    "A": {"variant": "v1", "strict_exact": False, "max_candidates": 8},
    # B: tek-tokenlik akronim alias'lari exact sayilmaz (sorgu-payi kurali).
    #    OLCULDU (yerel, 125 sorgu): 99 exact -> 44; 15 kisa/akronim sorgunun
    #    HICBIRI bozulmadi; hakemin gordugu liste 13 sorguda degisti.
    "B": {"variant": "v1", "strict_exact": True, "max_candidates": 8},
    # C: B + kirpma 12. 2026-07-24'te 8 secilmisti ("18 aday modeli yaniltiyor",
    #    TEK vaka, tezgahsiz); 2026-08-14 olcumu 8'in dogru kaydi kestigini
    #    gosterdi - 2 felaket vakayi kurtariyor. Ilk kez gercek veriyle sinaniyor.
    "C": {"variant": "v1", "strict_exact": True, "max_candidates": 12},
}


def _arm(name: str) -> dict:
    """Kol adiysa kol yapilandirmasi, degilse duz prompt varyanti + varsayilanlar."""
    if name in ARMS:
        return ARMS[name]
    get_variant(name)  # bilinmeyen ad burada patlar
    return {"variant": name, "strict_exact": False, "max_candidates": 8}

FIELDNAMES = [
    "run_id", "variant", "repeat_idx", "query", "sinif",
    # kolun retrieval/gorunum ayari - hangi ayarla uretildigi satirda dursun
    "prompt_variant", "strict_exact", "max_candidates",
    # --- kanit / izlenebilirlik ---
    "prompt_sha256", "schema_sha256", "prompt_chars", "model",
    # --- karar ---
    "status", "parent_verdict", "parent_id", "parent_name",
    "subunit_verdict", "subunit_id", "subunit_name", "unit_phrase",
    "error",
    # --- maliyet ---
    "resolve_s", "judge_s",
    # --- post-mortem ---
    "raw_response", "candidates_json",
]

# `diff`in karsilastirdigi alanlar. `status` dahil: hata da bir sonuctur
# (uyusmazlik hatasi kapandi mi sorusu tam olarak burada okunur).
COMPARE_KEYS = ("status", "parent_verdict", "parent_id", "subunit_verdict", "subunit_id")


class _RecordingClient:
    """Gercek client'i sarmalar, gordugu prompt/sema/ham yaniti kaydeder.

    Boylece `judge()`e provenans parametresi eklemeye gerek kalmaz - client
    zaten prompt'u ve semayi ARGUMAN olarak goruyor, ham yaniti da donduruyor.
    Uretim yolu bu yuzden hic degismedi.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.prompt: str | None = None
        self.schema: dict | None = None
        self.raw: str | None = None

    def generate(self, prompt: str, *, temperature: float = 0.0, format_schema=None) -> str:
        self.prompt, self.schema, self.raw = prompt, format_schema, None
        self.raw = self.inner.generate(prompt, temperature=temperature, format_schema=format_schema)
        return self.raw


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _candidates_json(result, max_candidates: int) -> str:
    """Hakemin GERCEKTEN gordugu aday listesi (kirpilmis goruntu)."""
    parents, subunits = build_candidate_views(result, max_candidates=max_candidates)

    def _v(c, kind):
        d = {"kind": kind, "id": c.id, "name": c.name, "tsr": round(c.token_set_ratio, 1),
             "bm25": round(c.bm25_norm, 3), "exact": c.exact_match,
             # exact'in HANGI metinle ve kac tokenla tuttugu - span-1 akronim
             # cakismalarini CSV'den olcebilmek icin (2026-08-14).
             "exact_text": c.exact_match_text,
             "exact_span": len((c.exact_match_text or "").split())}
        if kind == "parent":
            d["country"], d["city"] = c.country, c.city
        else:
            d["parent_id"], d["parent_name"] = c.parent_id, c.parent_name
        return d

    return json.dumps(
        [_v(c, "parent") for c in parents] + [_v(c, "subunit") for c in subunits],
        ensure_ascii=False,
    )


def _name_of(pool, matched_id):
    if not matched_id:
        return ""
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else ""


def _parse_plan(spec: str) -> list[tuple[str, int]]:
    """'A,B,C' ya da 'v1,v1,v3' -> [(ad, tekrar_idx), ...]"""
    seen: dict[str, int] = {}
    plan: list[tuple[str, int]] = []
    for name in [s.strip() for s in spec.split(",") if s.strip()]:
        _arm(name)  # bilinmeyen ad burada patlar, kosunun ortasinda degil
        idx = seen.get(name, 0)
        seen[name] = idx + 1
        plan.append((name, idx))
    if not plan:
        raise ValueError("bos varyant listesi")
    return plan


def cmd_run(args: argparse.Namespace) -> None:
    sample_path, out_path = Path(args.sample), Path(args.out)
    with sample_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    plan = _parse_plan(args.variants)

    done: set[tuple[str, str, str]] = set()
    existing = out_path.exists() and out_path.stat().st_size > 0
    if existing and args.resume:
        with out_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if list(reader.fieldnames or []) != FIELDNAMES:
                sys.exit("resume: mevcut CSV basligi uyusmuyor")
            done = {(r["query"], r["variant"], r["repeat_idx"]) for r in reader}
    elif existing:
        sys.exit(f"{out_path} zaten var - ustune yazmamak icin duruldu (--resume kullan)")

    # Tekrarlar AYRI GECISTE kosar (bkz. modul docstring'i 3): gecis 0'da her
    # sorgunun tum FARKLI varyantlari arka arkaya, gecis 1'de ikinci tekrarlar.
    passes: dict[int, list[str]] = {}
    for name, rep in plan:
        passes.setdefault(rep, []).append(name)

    run_id = uuid.uuid4().hex[:8]
    base_client = OllamaClient(model=args.model, host=args.host)
    client = _RecordingClient(base_client)

    # `resolve()` sorgu basina BIR KEZ - gecisler arasinda da tekrarlanmaz.
    # Onbellek anahtari (sorgu, strict_exact): ayni retrieval ayarini paylasan
    # kollar AYNI havuzu gorur (olcumun temizligi), farkli ayar ayri resolve ister.
    cache: dict[tuple, tuple] = {}

    def _get_pool(query: str, strict: bool):
        """(result, resolve_s) - hata durumunda (None, sure) + hata metni."""
        key = (query, strict)
        if key not in cache:
            t0 = time.time()
            try:
                res = _resolve(query, size=args.top, encode_prewarm=args.prewarm,
                               strict_exact=strict)
                cache[key] = (res, time.time() - t0, "")
            except Exception as exc:  # noqa: BLE001 - satir izolasyonu
                cache[key] = (None, time.time() - t0, f"resolve: {type(exc).__name__}: {exc}")
        return cache[key]

    todo_n = len(rows) * len(plan) - len(done)
    print(f"run_id={run_id}  {len(rows)} sorgu x {len(plan)} varyant = {todo_n} cagri  "
          f"({len(passes)} gecis)  model={args.model}", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if (existing and args.resume) else "w"
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()

        for rep in sorted(passes):
            names = passes[rep]
            print(f"\n=== GECIS {rep}: {', '.join(names)} ===", file=sys.stderr)
            for i, srow in enumerate(rows, start=1):
                query = srow["query"]
                todo = [n for n in names if (query, n, str(rep)) not in done]
                if not todo:
                    continue
                for name in todo:
                    cfg = _arm(name)
                    result, resolve_s, hata = _get_pool(query, cfg["strict_exact"])
                    rec = {k: "" for k in FIELDNAMES}
                    rec.update(run_id=run_id, variant=name, repeat_idx=rep, query=query,
                               sinif=srow.get("sinif", ""), model=args.model,
                               resolve_s=f"{resolve_s:.2f}",
                               prompt_variant=cfg["variant"],
                               strict_exact=str(cfg["strict_exact"]),
                               max_candidates=str(cfg["max_candidates"]))
                    if result is None:  # resolve patladi - hakem hic cagrilmaz
                        rec.update(status="error", error=hata[:300])
                        writer.writerow(rec)
                        continue
                    rec["candidates_json"] = _candidates_json(result, cfg["max_candidates"])
                    t1 = time.time()
                    try:
                        v = _judge(result, client, variant=get_variant(cfg["variant"]),
                                   max_candidates=cfg["max_candidates"])
                        rec["status"] = "ok"
                        rec["parent_verdict"] = v.parent.verdict
                        rec["parent_id"] = v.parent.matched_id or ""
                        rec["parent_name"] = _name_of(result.parents, v.parent.matched_id)
                        if v.subunit is not None:
                            rec["subunit_verdict"] = v.subunit.verdict
                            rec["subunit_id"] = v.subunit.matched_id or ""
                            rec["subunit_name"] = _name_of(result.subunits, v.subunit.matched_id)
                        rec["unit_phrase"] = v.unit_phrase or ""
                    except (JudgeValidationError, LlmError) as exc:
                        rec["status"] = "error"
                        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
                    except Exception as exc:  # noqa: BLE001 - satir izolasyonu
                        rec["status"] = "error"
                        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
                    rec["judge_s"] = f"{time.time() - t1:.2f}"
                    # Prompt/sema/ham yanit hata durumunda da yazilir - post-mortem
                    # tam da o satirlar icin lazim.
                    if client.prompt is not None:
                        rec["prompt_sha256"] = _sha(client.prompt)
                        rec["prompt_chars"] = str(len(client.prompt))
                    if client.schema is not None:
                        rec["schema_sha256"] = _sha(json.dumps(client.schema, sort_keys=True))
                    rec["raw_response"] = (client.raw or "")[:2000]
                    writer.writerow(rec)
                f.flush()
                print(f"[g{rep} {i}/{len(rows)}] {query[:44]!r:<48} {' | '.join(todo)}",
                      file=sys.stderr)

    base_client.close()
    print(f"\nBITTI -> {out_path}", file=sys.stderr)


def _load_side(run_rows: list[dict], spec: str, sample: dict[str, dict]) -> dict[str, dict]:
    """'v1#0' -> o kosunun {query: satir} haritasi. 'kaggle' -> ornekemdeki taban."""
    if spec == "kaggle":
        return {
            q: {"status": r["kaggle_status"],
                "parent_verdict": r["kaggle_parent_verdict"],
                "parent_id": r["kaggle_parent_id"],
                "parent_name": r["kaggle_parent_name"],
                "subunit_verdict": r["kaggle_subunit_verdict"],
                "subunit_id": r["kaggle_subunit_id"],
                "sinif": r["sinif"]}
            for q, r in sample.items()
        }
    name, _, idx = spec.partition("#")
    idx = idx or "0"
    out = {r["query"]: r for r in run_rows if r["variant"] == name and r["repeat_idx"] == idx}
    if not out:
        sys.exit(f"kosuda {spec!r} bulunamadi")
    return out


def cmd_diff(args: argparse.Namespace) -> None:
    with Path(args.run).open(newline="", encoding="utf-8") as f:
        run_rows = list(csv.DictReader(f))
    with Path(args.sample).open(newline="", encoding="utf-8") as f:
        sample = {r["query"]: r for r in csv.DictReader(f)}

    A = _load_side(run_rows, args.a, sample)
    B = _load_side(run_rows, args.b, sample)
    common = [q for q in A if q in B]

    per_class: dict[str, list[int]] = {}
    deltas: list[dict] = []
    for q in common:
        a, b = A[q], B[q]
        sinif = sample.get(q, {}).get("sinif", "?")
        changed = [k for k in COMPARE_KEYS if (a.get(k) or "") != (b.get(k) or "")]
        stat = per_class.setdefault(sinif, [0, 0])
        stat[1] += 1
        if changed:
            stat[0] += 1
            deltas.append({
                "query": q, "sinif": sinif, "degisen": ",".join(changed),
                "A_status": a.get("status", ""), "B_status": b.get("status", ""),
                "A_parent": f"{a.get('parent_verdict','')}/{a.get('parent_id','')} {a.get('parent_name','')}",
                "B_parent": f"{b.get('parent_verdict','')}/{b.get('parent_id','')} {b.get('parent_name','')}",
                "A_subunit": f"{a.get('subunit_verdict','')}/{a.get('subunit_id','')}",
                "B_subunit": f"{b.get('subunit_verdict','')}/{b.get('subunit_id','')}",
            })

    print(f"\n{args.a}  <->  {args.b}     ortak sorgu: {len(common)}\n")
    print(f"{'sinif':<20} {'degisen':>8} {'toplam':>7} {'oran':>7}")
    print("-" * 46)
    tot_c = tot_n = 0
    for sinif, (c, n) in sorted(per_class.items()):
        tot_c, tot_n = tot_c + c, tot_n + n
        print(f"{sinif:<20} {c:>8} {n:>7} {c / n:>6.1%}")
    print("-" * 46)
    print(f"{'TOPLAM':<20} {tot_c:>8} {tot_n:>7} {tot_c / tot_n if tot_n else 0:>6.1%}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.out).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(deltas[0].keys()) if deltas else ["query"])
            w.writeheader()
            w.writerows(deltas)
        print(f"\nfarklar -> {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="varyantlari kosur")
    r.add_argument("--sample", default=DEFAULT_SAMPLE)
    r.add_argument("--variants", default="v1,v1")
    r.add_argument("--out", required=True)
    r.add_argument("--model", default="gemma4:e4b")
    r.add_argument("--host", default="http://localhost:11434")
    r.add_argument("--top", type=int, default=5)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--resume", action="store_true")
    # Envanter modu (Kaggle tabaninin uretildigi yol) prewarm ACIK kosuyor -
    # havuzlarin tabanla karsilastirilabilir olmasi icin varsayilan da acik.
    r.add_argument("--no-prewarm", dest="prewarm", action="store_false", default=True)
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("diff", help="iki kosuyu/varyanti karsilastirir")
    d.add_argument("--run", required=True)
    d.add_argument("--sample", default=DEFAULT_SAMPLE)
    d.add_argument("--a", required=True, help="ör. v1#0")
    d.add_argument("--b", required=True, help="ör. v1#1 ya da 'kaggle'")
    d.add_argument("--out", default=None, help="fark CSV yolu")
    d.set_defaults(func=cmd_diff)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
