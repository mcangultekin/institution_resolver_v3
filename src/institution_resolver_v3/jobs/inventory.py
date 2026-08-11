"""Envanter modu - `institution-field-inventory.csv`'nin parent'i BOS satirlari icin.

Normal `decide()` akisindan UC noktada ayrilir (hepsi bu is icin olculdu,
2026-08-11, 500 sorguluk gercek ornek):

1. **Subunit hakeme GITMEZ.** `decide()` parent VEYA subunit auto_match degilse
   tum sorguyu LLM'e devreder; bu sette hakeme dusen pay %78,4 cikiyor. Yalniz
   parent'a bakildiginda %52,0. Yani subunit'i tetikleyici olmaktan cikarmak
   hakem cagrilarinin ucte birini eliyor (~63 gun -> ~41 gun).
   Subunit yalnizca gate `auto_match` derse KARAR olarak yazilir.

   NOT: parent yuzunden hakem zaten calistiysa, judge() ikisine BIRLIKTE karar
   verdigi icin subunit cevabi bedava gelir - o zaman kullanilir ve
   `subunit_decided_by=judge` diye isaretlenir. Kural "subunit ICIN LLM'e
   gitme"dir, "hakem calistiysa cevabini at" degil.

2. **Sorgu-ici toplu kodlama** (`encode_prewarm=True`). Bir resolve()'da ~3,5 ayri
   metin kodlaniyordu, her biri ayri transformer gecisiyle (18,9 ms/metin);
   tek batch'te 5,2 ms/metin. Cekirdekte VARSAYILAN KAPALI - vektorler batch'te
   ~3e-07 sapiyor (kosinus 0,9999998), o yuzden normal akis degismesin diye
   yalniz burada aciliyor.

3. **Karara girmeyen en iyi aday da yazilir.** auto_match cikmayan taraf icin
   `*_cand_*` kolonlari gate'in top-1 onerisini tasir - satir kuyruga dusse bile
   veri kaybolmaz, ikinci tur icin yeniden resolve gerekmez.

`--no-judge` ile LLM tamamen devre disi birakilabilir (tam kosu ~22 saat);
kalan `review`/`ambiguous` satirlar sonra ayri bir hakem turuna verilir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from institution_resolver_v3.eval.csv_runner import ProgressFn, run_csv_batch
from institution_resolver_v3.gate.gate import GateDecision, GateResult
from institution_resolver_v3.gate.gate import gate as _gate
from institution_resolver_v3.judge.judge import judge as _judge
from institution_resolver_v3.retrieve.resolve import resolve as _resolve

FIELDNAMES = [
    "query",
    "normalized_name",  # girdi CSV'sinden gecirilir - envantere geri-join anahtari
    "rows",             # bu adin temsil ettigi bos satir sayisi (oncelik/etki)
    "status",           # ok | error
    # --- nihai kararlar (envantere yazilacak olanlar) ---
    "parent_verdict",
    "parent_id",
    "parent_name",
    "parent_confidence",
    "parent_decided_by",   # gate | judge | (bos: karar yok)
    "subunit_verdict",
    "subunit_id",
    "subunit_name",
    "subunit_confidence",
    "subunit_decided_by",
    # --- karara girmeyen en iyi adaylar (kuyruk/ikinci tur icin) ---
    "parent_cand_id",
    "parent_cand_name",
    "parent_cand_conf",
    "subunit_cand_id",
    "subunit_cand_name",
    "subunit_cand_conf",
    # --- denetim ---
    "gate_parent_verdict",
    "gate_subunit_verdict",
    "unit_phrase",
    "needs_review",     # 1 = insan kuyruguna dussun
    "judged",           # 1 = LLM hakem calisti
    "resolve_s",
    "gate_s",
    "judge_s",
    "error",
    "result_json",
]

# Gate karari nihai sayilan etiketler: bu ikisi disinda parent hakeme gider.
_SETTLED = ("auto_match", "no_match")


def _name_of(pool: list, matched_id: str | None) -> str:
    if matched_id is None:
        return ""
    c = next((c for c in pool if c.id == matched_id), None)
    return c.name if c else ""


def _display_of(pool: list):
    """Gate'in 'gosterim adayi' ile AYNI secim: en yuksek token_set_ratio.

    Gate `review`/`no_match`in "exact yok" dalinda `matched_id=None` dondurur
    (gate.py `_decide_pool`) - aday yalnizca sinyallerde kalir. Kuyruk/ikinci tur
    icin adayin KIMLIGI de lazim oldugundan havuzdan ayni kayda geri donuyoruz.
    """
    return max(pool, key=lambda c: c.token_set_ratio, default=None)


def _blank_record(query: str) -> dict[str, str]:
    return {k: "" for k in FIELDNAMES} | {"query": query, "status": "ok"}


def _write_side(
    rec: dict[str, str],
    side: str,
    decision: GateDecision | None,
    pool: list,
    *,
    accepted: bool,
    decided_by: str,
) -> None:
    """Bir tarafi (parent/subunit) kayda yazar.

    `accepted=True` -> karar kolonlarina; degilse yalniz `*_cand_*` adayina.
    Ikisi ayri tutuluyor ki "sistem ne dedi" ile "envantere ne yazilacak"
    birbirine karismasin.
    """
    if decision is None:
        return
    conf = f"{decision.confidence:.3f}"
    rec[f"{side}_verdict"] = decision.verdict
    if accepted and decision.matched_id:
        rec[f"{side}_id"] = decision.matched_id
        rec[f"{side}_name"] = _name_of(pool, decision.matched_id)
        rec[f"{side}_confidence"] = conf
        rec[f"{side}_decided_by"] = decided_by
        return
    # Karar yok: aday kolonlarina yaz. matched_id bos olabilir ("exact yok"
    # dali) - o zaman gate'in gosterim adayina geri dus, yoksa satir kuyruga
    # kimliksiz duser ve ikinci turda bastan resolve gerekir.
    if decision.matched_id:
        rec[f"{side}_cand_id"] = decision.matched_id
        rec[f"{side}_cand_name"] = _name_of(pool, decision.matched_id)
    else:
        best = _display_of(pool)
        rec[f"{side}_cand_id"] = best.id if best else ""
        rec[f"{side}_cand_name"] = best.name if best else ""
    rec[f"{side}_cand_conf"] = conf


def process_one_inventory(
    query: str,
    *,
    client: Any = None,
    judge_enabled: bool = True,
    resolve_fn: Callable = _resolve,
    gate_fn: Callable = _gate,
    judge_fn: Callable = _judge,
    top: int = 5,
    context: dict[str, str] | None = None,
) -> dict[str, str]:
    """Tek sorgu: resolve -> gate -> (gerekiyorsa yalniz PARENT icin) hakem.

    `context`: girdi CSV'sinden tasinacak alanlar (normalized_name, rows).
    Hata satir bazinda yakalanir - 287 bin satirlik kosu tek sorgu yuzunden
    durmasin (eval/batch.py ile ayni ilke).
    """
    rec = _blank_record(query)
    if context:
        rec["normalized_name"] = context.get("normalized_name", "")
        rec["rows"] = context.get("rows", "")
    try:
        t0 = time.time()
        res = resolve_fn(query, size=top, encode_prewarm=True)
        rec["resolve_s"] = f"{time.time() - t0:.2f}"

        t1 = time.time()
        g: GateResult = gate_fn(res)
        rec["gate_s"] = f"{time.time() - t1:.2f}"
        rec["gate_parent_verdict"] = g.parent.verdict
        rec["gate_subunit_verdict"] = g.subunit.verdict if g.subunit else ""
        rec["unit_phrase"] = g.unit_phrase or ""

        parent_settled = g.parent.verdict in _SETTLED
        judged = False
        j = None

        if not parent_settled and judge_enabled and client is not None:
            t2 = time.time()
            j = judge_fn(res, client)
            rec["judge_s"] = f"{time.time() - t2:.2f}"
            judged = True

        rec["judged"] = "1" if judged else "0"

        if judged and j is not None:
            _write_side(rec, "parent", j.parent, res.parents, accepted=True, decided_by="judge")
            # Hakem calistiysa subunit cevabi bedava - kural "subunit ICIN LLM'e
            # gitme"ydi, gelen cevabi atmak degil (bkz. modul docstring 1).
            if j.subunit is not None:
                _write_side(
                    rec, "subunit", j.subunit, res.subunits, accepted=True, decided_by="judge"
                )
            elif g.subunit is not None:
                _write_side(rec, "subunit", g.subunit, res.subunits, accepted=False, decided_by="")
            rec["needs_review"] = "0" if j.parent.verdict in _SETTLED else "1"
        else:
            _write_side(
                rec, "parent", g.parent, res.parents,
                accepted=parent_settled, decided_by="gate",
            )
            # Subunit: YALNIZ gate auto_match ise karar; digerleri aday olarak durur.
            if g.subunit is not None:
                _write_side(
                    rec, "subunit", g.subunit, res.subunits,
                    accepted=g.subunit.verdict == "auto_match", decided_by="gate",
                )
            rec["needs_review"] = "0" if parent_settled else "1"

        rec["result_json"] = json.dumps(
            {
                "gate": {
                    "parent": {"verdict": g.parent.verdict, "id": g.parent.matched_id,
                               "signals": g.parent.signals},
                    "subunit": (None if g.subunit is None else
                                {"verdict": g.subunit.verdict, "id": g.subunit.matched_id,
                                 "signals": g.subunit.signals}),
                },
                "judge": (None if j is None else
                          {"parent": {"verdict": j.parent.verdict, "id": j.parent.matched_id},
                           "subunit": (None if j.subunit is None else
                                       {"verdict": j.subunit.verdict, "id": j.subunit.matched_id})}),
                "unit_phrase": g.unit_phrase,
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001 - satir izolasyonu; kosu surmeli
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return rec


def run_inventory_batch(
    rows: Iterable[dict[str, str]],
    out_path: str | Path,
    *,
    client: Any = None,
    judge_enabled: bool = True,
    resolve_fn: Callable = _resolve,
    gate_fn: Callable = _gate,
    judge_fn: Callable = _judge,
    top: int = 5,
    limit: int | None = None,
    resume: bool = False,
    on_progress: ProgressFn | None = None,
    max_workers: int = 1,
) -> dict[str, Any]:
    """Girdi satirlarini (query + normalized_name + rows) isleyip CSV'ye yazar.

    `rows` iki kez gezilir (context haritasi + sorgu akisi), o yuzden liste
    olarak toplanir - girdi 287 bin satirda ~50 MB, kabul edilebilir.

    `max_workers>1`: ES cagrisi IO-bound oldugu icin `ThreadPoolExecutor`
    havuzunda es-zamanli calisir (bkz. `run_csv_batch`). Olculdu (2026-08-11,
    300 sorguluk dilim, --no-judge): 1 isci 0,333 sn/sorgu, 4 isci 0,149
    sn/sorgu (~2,2x), 8 iscide kazanc geriliyor (0,164) - 4 civari tavan.
    Kararlar isci sayisindan bagimsiz birebir ayni cikti (0 fark, 300/300).
    """
    rows = list(rows)
    ctx = {
        r["query"]: {"normalized_name": r.get("normalized_name", ""), "rows": r.get("rows", "")}
        for r in rows
    }

    def _proc(query: str) -> dict[str, str]:
        return process_one_inventory(
            query,
            client=client,
            judge_enabled=judge_enabled,
            resolve_fn=resolve_fn,
            gate_fn=gate_fn,
            judge_fn=judge_fn,
            top=top,
            context=ctx.get(query),
        )

    return run_csv_batch(
        (r["query"] for r in rows),
        out_path,
        FIELDNAMES,
        _proc,
        limit=limit,
        resume=resume,
        on_progress=on_progress,
        max_workers=max_workers,
    )
