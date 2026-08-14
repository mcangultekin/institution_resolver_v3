"""A/B tezgahi (scripts/judge_ab.py) - LLM'siz, sahte client ile.

Tezgahin iki olcum garantisini kilitler:
1. `resolve()` sorgu basina BIR KEZ kosar, tum varyantlar AYNI havuzu gorur
2. Varyantlar sorgu basina arka arkaya kosar (zaman kaymasi esit dagilsin)
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "judge_ab.py"
_spec = importlib.util.spec_from_file_location("judge_ab", _PATH)
judge_ab = importlib.util.module_from_spec(_spec)
sys.modules["judge_ab"] = judge_ab
_spec.loader.exec_module(judge_ab)


class TestPlanParsing:
    def test_repeat_indices(self):
        assert judge_ab._parse_plan("v1,v1,v3") == [("v1", 0), ("v1", 1), ("v3", 0)]

    def test_single(self):
        assert judge_ab._parse_plan("v1") == [("v1", 0)]

    def test_unknown_fails_before_run(self):
        """Bilinmeyen varyant kosunun ORTASINDA degil, basinda patlamali."""
        with pytest.raises(KeyError):
            judge_ab._parse_plan("v1,yok")

    def test_empty(self):
        with pytest.raises(ValueError):
            judge_ab._parse_plan("  ")


def _fake_result(query="ege universitesi tip fakultesi"):
    hyp = BoundaryHypothesis("ege universitesi", "tip fakultesi", 95.0, "EGE ÜNİVERSİTESİ", "152")
    dq = DecomposedQuery(hyp.institution_part, hyp.unit_part, hyp.boundary_score,
                         hyp.matched_parent_name, hyp.matched_parent_id, hypotheses=[hyp])
    parents = [ScoredCandidate(id="152", record_type="parent", name="EGE ÜNİVERSİTESİ",
                               raw={"id": "152", "country": "TR", "city": "İzmir"},
                               bm25_norm=1.0, cosine=None, token_set_ratio=97.0,
                               qualifier_conflict=False, exact_match=True,
                               exact_match_text="ege universitesi")]
    subs = [ScoredCandidate(id="900", record_type="subunit", name="TIP FAKÜLTESİ",
                            raw={"id": "900", "parent_id": "152", "parent_name": "EGE ÜNİVERSİTESİ"},
                            bm25_norm=0.9, cosine=None, token_set_ratio=80.0,
                            qualifier_conflict=False)]
    return ResolveResult(query=query, decomposed=dq, parents=parents, subunits=subs)


class _FakeInner:
    """Her cagride ayni gecerli yaniti doner, gordugu prompt'lari biriktirir."""

    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt, *, temperature=0.0, format_schema=None):
        self.prompts.append(prompt)
        return json.dumps({"parent": {"verdict": "auto_match", "matched_id": "P1|EGE ÜNİVERSİTESİ"},
                           "unit_phrase": "tip fakultesi",
                           "subunit": {"verdict": "auto_match", "matched_id": "S1|TIP FAKÜLTESİ"}})


class TestRecordingClient:
    def test_captures_prompt_schema_raw(self):
        inner = _FakeInner()
        c = judge_ab._RecordingClient(inner)
        out = c.generate("merhaba", format_schema={"type": "object"})
        assert c.prompt == "merhaba"
        assert c.schema == {"type": "object"}
        assert c.raw == out

    def test_resets_between_calls(self):
        inner = _FakeInner()
        c = judge_ab._RecordingClient(inner)
        c.generate("bir", format_schema={"a": 1})
        c.generate("iki", format_schema={"b": 2})
        assert c.prompt == "iki" and c.schema == {"b": 2}


class TestRunLoop:
    """`cmd_run`u sahte resolve/client ile kosup CSV'yi dogrular."""

    def _run(self, tmp_path, monkeypatch, variants="v1,v1,v3", n_queries=2):
        sample = tmp_path / "ornek.csv"
        with sample.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["sinif", "query"])
            w.writeheader()
            for i in range(n_queries):
                w.writerow({"sinif": "auto_match", "query": f"sorgu {i}"})

        calls = {"resolve": 0}

        def fake_resolve(query, *, size=5, encode_prewarm=False, strict_exact=False):
            calls["resolve"] += 1
            calls.setdefault("strict", []).append(strict_exact)
            return _fake_result(query)

        inner = _FakeInner()
        monkeypatch.setattr(judge_ab, "_resolve", fake_resolve)
        monkeypatch.setattr(judge_ab, "OllamaClient", lambda **kw: inner)
        monkeypatch.setattr(inner, "close", lambda: None, raising=False)

        out = tmp_path / "ab.csv"
        args = judge_ab.argparse.Namespace(
            sample=str(sample), variants=variants, out=str(out), model="test",
            host="http://x", top=5, limit=None, resume=False, prewarm=False,
        )
        judge_ab.cmd_run(args)
        with out.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f)), calls, inner

    def test_resolve_called_once_per_query(self, tmp_path, monkeypatch):
        """ASIL GARANTI: 2 sorgu x 3 varyant = 6 hakem cagrisi ama 2 resolve."""
        rows, calls, inner = self._run(tmp_path, monkeypatch)
        assert calls["resolve"] == 2
        assert len(rows) == 6
        assert len(inner.prompts) == 6

    def test_all_variants_see_same_pool(self, tmp_path, monkeypatch):
        rows, _, _ = self._run(tmp_path, monkeypatch)
        for query in {r["query"] for r in rows}:
            pools = {r["candidates_json"] for r in rows if r["query"] == query}
            assert len(pools) == 1, "varyantlar farkli havuz gordu"

    def test_distinct_variants_interleaved_repeats_separate_pass(self, tmp_path, monkeypatch):
        """FARKLI varyantlar sorgu basina arka arkaya (zaman kaymasi esit dagilsin);
        TEKRARLAR ayri geciste (KV-cache pes pese tekrari yapay olarak deterministik
        yapiyor - canli olculdu 21,97sn -> 2,03sn, bkz. judge_ab.py docstring)."""
        rows, _, _ = self._run(tmp_path, monkeypatch)
        order = [(r["query"], r["variant"], r["repeat_idx"]) for r in rows]
        assert order == [
            # gecis 0: her sorgu icin v1#0 ve v3#0 arka arkaya
            ("sorgu 0", "v1", "0"), ("sorgu 0", "v3", "0"),
            ("sorgu 1", "v1", "0"), ("sorgu 1", "v3", "0"),
            # gecis 1: tekrarlar, tum sorgular yeniden gezilerek
            ("sorgu 0", "v1", "1"), ("sorgu 1", "v1", "1"),
        ]

    def test_repeat_not_adjacent_to_its_first_run(self, tmp_path, monkeypatch):
        """Ayni (sorgu, varyant) ciftinin iki tekrari ARDIŞIK OLMAMALI."""
        rows, _, _ = self._run(tmp_path, monkeypatch)
        for a, b in zip(rows, rows[1:]):
            assert not (a["query"] == b["query"] and a["variant"] == b["variant"])

    def test_v1_and_v3_prompts_differ(self, tmp_path, monkeypatch):
        rows, _, _ = self._run(tmp_path, monkeypatch)
        h = {r["variant"]: r["prompt_sha256"] for r in rows}
        assert h["v1"] != h["v3"]

    def test_v1_repeats_have_identical_prompt(self, tmp_path, monkeypatch):
        """Gurultu tabani olcumunun on kosulu: v1#0 ve v1#1 BIREBIR ayni prompt."""
        rows, _, _ = self._run(tmp_path, monkeypatch)
        for query in {r["query"] for r in rows}:
            h = {r["prompt_sha256"] for r in rows if r["query"] == query and r["variant"] == "v1"}
            assert len(h) == 1

    def test_provenance_columns_filled(self, tmp_path, monkeypatch):
        rows, _, _ = self._run(tmp_path, monkeypatch)
        for r in rows:
            assert r["prompt_sha256"] and r["schema_sha256"] and r["prompt_chars"]
            assert r["raw_response"] and r["candidates_json"]
            assert r["run_id"]


class TestDiff:
    def _write_run(self, path, rows):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=judge_ab.FIELDNAMES)
            w.writeheader()
            for r in rows:
                w.writerow({**{k: "" for k in judge_ab.FIELDNAMES}, **r})

    def test_detects_changed_decisions(self, tmp_path, capsys):
        run = tmp_path / "ab.csv"
        self._write_run(run, [
            {"query": "a", "variant": "v1", "repeat_idx": "0", "status": "ok",
             "parent_verdict": "auto_match", "parent_id": "1", "sinif": "auto_match"},
            {"query": "a", "variant": "v1", "repeat_idx": "1", "status": "ok",
             "parent_verdict": "no_match", "parent_id": "", "sinif": "auto_match"},
            {"query": "b", "variant": "v1", "repeat_idx": "0", "status": "ok",
             "parent_verdict": "auto_match", "parent_id": "2", "sinif": "auto_match"},
            {"query": "b", "variant": "v1", "repeat_idx": "1", "status": "ok",
             "parent_verdict": "auto_match", "parent_id": "2", "sinif": "auto_match"},
        ])
        sample = tmp_path / "ornek.csv"
        with sample.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["sinif", "query"])
            w.writeheader()
            w.writerow({"sinif": "auto_match", "query": "a"})
            w.writerow({"sinif": "auto_match", "query": "b"})

        delta = tmp_path / "fark.csv"
        judge_ab.cmd_diff(judge_ab.argparse.Namespace(
            run=str(run), sample=str(sample), a="v1#0", b="v1#1", out=str(delta)))
        out = capsys.readouterr().out
        assert "50.0%" in out  # 2 sorgudan 1'i degisti
        with delta.open(encoding="utf-8") as f:
            deltas = list(csv.DictReader(f))
        assert len(deltas) == 1 and deltas[0]["query"] == "a"

    def test_missing_side_exits(self, tmp_path):
        run = tmp_path / "ab.csv"
        self._write_run(run, [{"query": "a", "variant": "v1", "repeat_idx": "0"}])
        sample = tmp_path / "ornek.csv"
        with sample.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["sinif", "query"])
            w.writeheader()
            w.writerow({"sinif": "x", "query": "a"})
        with pytest.raises(SystemExit):
            judge_ab.cmd_diff(judge_ab.argparse.Namespace(
                run=str(run), sample=str(sample), a="v1#0", b="v9#0", out=None))


class TestArms:
    """Kol = prompt varyanti + retrieval/gorunum ayari (2026-08-14).

    Felaket vakalarin sebebi prompt degil HAVUZ GORUNUMU cikti (dogru kayit
    havuzun 8./10. sirasindaydi, kirpma 8'de kesiyordu), o yuzden tezgahin
    yalniz prompt'u degil retrieval ayarini da degistirebilmesi gerekiyor.
    """

    def test_registry(self):
        assert judge_ab._arm("A") == {"variant": "v1", "strict_exact": False, "max_candidates": 8}
        assert judge_ab._arm("B")["strict_exact"] is True
        assert judge_ab._arm("C")["max_candidates"] == 12

    def test_plain_variant_still_works(self):
        """Kol adi olmayan ad duz prompt varyanti sayilir - eski kullanim bozulmaz."""
        assert judge_ab._arm("v4") == {"variant": "v4", "strict_exact": False, "max_candidates": 8}

    def test_unknown_name_fails_early(self):
        with pytest.raises(KeyError):
            judge_ab._parse_plan("A,yok")

    def test_arms_sharing_retrieval_config_share_pool(self, tmp_path, monkeypatch):
        """B ve C ayni `strict_exact` kullanir -> TEK resolve; A farkli -> ayri resolve.
        Yani 1 sorgu icin 2 resolve, 3 hakem cagrisi."""
        rows, calls, _ = self._run_arms(tmp_path, monkeypatch, "A,B,C", n_queries=1)
        assert calls["resolve"] == 2
        assert len(rows) == 3
        assert sorted(calls["strict"]) == [False, True]

    def test_config_recorded_per_row(self, tmp_path, monkeypatch):
        rows, _, _ = self._run_arms(tmp_path, monkeypatch, "A,B,C", n_queries=1)
        by = {r["variant"]: r for r in rows}
        assert by["A"]["strict_exact"] == "False" and by["A"]["max_candidates"] == "8"
        assert by["B"]["strict_exact"] == "True" and by["B"]["max_candidates"] == "8"
        assert by["C"]["strict_exact"] == "True" and by["C"]["max_candidates"] == "12"
        assert all(r["prompt_variant"] == "v1" for r in rows)

    def test_exact_span_in_candidates_json(self, tmp_path, monkeypatch):
        """span-1 akronim cakismalarini CSV'den olcebilmek icin."""
        rows, _, _ = self._run_arms(tmp_path, monkeypatch, "A", n_queries=1)
        c = json.loads(rows[0]["candidates_json"])[0]
        assert "exact_text" in c and "exact_span" in c

    _run_arms = TestRunLoop._run
