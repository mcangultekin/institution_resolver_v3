"""Bagli sema (v5-bagli) + koda tasinan kafa-karisikligi dedektoru.

Kapattigi defekt uretimde OLCULDU: `parent` ve `subunit` enum'lari bagimsiz
oldugu icin model tutarsiz cift secebiliyor ve `_validate_ids` TUM SATIRI
dusuruyordu - 3000 sorguda 232 satir (%7,7), envanterde 34.299 satir.
Hatalarin DETERMINISTIK oldugu 14 Agustos'ta dogrulandi (ayni sorgular her
kosuda ayni sekilde patliyor), yani retry degil sema cozer.
"""

from __future__ import annotations

import json

import pytest

from institution_resolver_v3.judge.candidates import CandidateView
from institution_resolver_v3.judge.judge import (
    JudgeValidationError,
    _confusion_signal,
    build_format_schema,
    judge,
)
from institution_resolver_v3.judge.prompt import build_prompt
from institution_resolver_v3.judge.schema import JudgeResult
from institution_resolver_v3.judge.variants import V1, V4, V5
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate


def _views():
    parents = [
        CandidateView(id="P1", name="EGE ÜNİVERSİTESİ", bm25_norm=1.0, cosine=None,
                      token_set_ratio=97.0, qualifier_conflict=False, passed_parent_filter=None),
        CandidateView(id="P2", name="GAZİ ÜNİVERSİTESİ", bm25_norm=0.8, cosine=None,
                      token_set_ratio=70.0, qualifier_conflict=False, passed_parent_filter=None),
    ]
    subunits = [
        CandidateView(id="S1", name="EGE TIP", bm25_norm=0.9, cosine=None, token_set_ratio=80.0,
                      qualifier_conflict=False, passed_parent_filter=True, parent_id="152"),
        CandidateView(id="S2", name="GAZİ TIP", bm25_norm=0.7, cosine=None, token_set_ratio=60.0,
                      qualifier_conflict=False, passed_parent_filter=False, parent_id="999"),
        CandidateView(id="S3", name="ÖKSÜZ BİRİM", bm25_norm=0.5, cosine=None, token_set_ratio=40.0,
                      qualifier_conflict=False, passed_parent_filter=False, parent_id="7777"),
    ]
    return parents, subunits, {"P1": "152", "P2": "999"}


class TestBoundSchemaShape:
    def test_one_branch_per_parent_plus_no_match(self):
        p, s, m = _views()
        sch = build_format_schema(p, s, variant=V5, parent_real_ids=m)
        assert "anyOf" in sch
        assert len(sch["anyOf"]) == 3  # no_match + 2 parent

    def test_subunit_enum_locked_to_chosen_parent(self):
        """ASIL GARANTI: P1 dalinda YALNIZ 152'ye bagli subunit secilebilir."""
        p, s, m = _views()
        sch = build_format_schema(p, s, variant=V5, parent_real_ids=m)
        dal = next(
            b for b in sch["anyOf"]
            if b["properties"]["parent"].get("properties", {}).get("matched_id", {}).get("const", "")
            .startswith("P1|")
        )
        secenekler = [
            o for o in dal["properties"]["subunit"]["anyOf"]
            if "anyOf" in o or "properties" in o
        ]
        metin = json.dumps(secenekler, ensure_ascii=False)
        assert "S1|EGE TIP" in metin
        assert "S2|GAZİ TIP" not in metin      # baska parent'in birimi
        assert "S3|ÖKSÜZ BİRİM" not in metin   # havuzda parent'i olmayan

    def test_orphan_subunit_unreachable_in_every_branch(self):
        """Parent'i aday listesinde olmayan subunit HICBIR dalda gorunmez -
        bilincli daralma (bkz. variants.py YAPISAL YAN ETKI)."""
        p, s, m = _views()
        metin = json.dumps(build_format_schema(p, s, variant=V5, parent_real_ids=m),
                           ensure_ascii=False)
        assert "ÖKSÜZ BİRİM" not in metin

    def test_no_match_branch_forbids_subunit_identity(self):
        p, s, m = _views()
        sch = build_format_schema(p, s, variant=V5, parent_real_ids=m)
        dal = next(b for b in sch["anyOf"]
                   if b["properties"]["parent"]["properties"]["verdict"] == {"const": "no_match"})
        metin = json.dumps(dal["properties"]["subunit"], ensure_ascii=False)
        assert "S1" not in metin and "S2" not in metin

    def test_unbound_variants_unchanged(self):
        """v1/v4 semasi DEGISMEMELI - bagli sema yalniz v5'te devrede."""
        p, s, m = _views()
        taban = build_format_schema(p, s)
        assert build_format_schema(p, s, variant=V1, parent_real_ids=m) == taban
        assert build_format_schema(p, s, variant=V4, parent_real_ids=m) == taban
        assert "anyOf" not in taban  # ust seviye anyOf yok


class TestBoundPrompt:
    def test_contradictory_sentence_replaced(self):
        """Bagli semada 'AYRI ayri ver' cumlesi YALAN olur - degistirilmeli."""
        from tests.unit.test_judge_variants import _fixture  # noqa: PLC0415

        q, dq, p, s = _fixture()
        out = build_prompt(q, dq, p, s, variant=V5)
        assert "kararını AYRI ayrı ver" not in out
        assert "ÖNCE kurumu (parent) seç" in out
        assert "başka bir kurumun birimini seçemezsin" in out

    def test_v4_keeps_original_sentence(self):
        from tests.unit.test_judge_variants import _fixture  # noqa: PLC0415

        q, dq, p, s = _fixture()
        assert "kararını AYRI ayrı ver" in build_prompt(q, dq, p, s, variant=V4)


class TestConfusionSignal:
    def _res(self, parent_id, sub_id):
        return JudgeResult.model_validate({
            "parent": {"verdict": "auto_match", "matched_id": parent_id},
            "unit_phrase": "tip",
            "subunit": {"verdict": "auto_match", "matched_id": sub_id},
        })

    def test_fires_when_strongest_evidence_points_elsewhere(self):
        _, s, _ = _views()
        s[1].exact_match = True  # GAZİ TIP en guclu kanit ama parent EGE secildi
        assert _confusion_signal(self._res("152", "S1"), s, "152") is True

    def test_silent_when_strongest_evidence_matches(self):
        _, s, _ = _views()
        assert _confusion_signal(self._res("152", "S1"), s, "152") is False

    def test_silent_without_subunit_choice(self):
        _, s, _ = _views()
        r = JudgeResult.model_validate({"parent": {"verdict": "auto_match", "matched_id": "152"},
                                        "subunit": None})
        assert _confusion_signal(r, s, "152") is False


class _Fake:
    def __init__(self, payload):
        self.payload = payload
        self.schema = None

    def generate(self, prompt, *, temperature=0.0, format_schema=None):
        self.schema = format_schema
        return json.dumps(self.payload)


def _resolve_result():
    hyp = BoundaryHypothesis("ege universitesi", "tip", 95.0, "EGE ÜNİVERSİTESİ", "152")
    dq = DecomposedQuery(hyp.institution_part, hyp.unit_part, hyp.boundary_score,
                         hyp.matched_parent_name, hyp.matched_parent_id, hypotheses=[hyp])
    parents = [ScoredCandidate(id="152", record_type="parent", name="EGE ÜNİVERSİTESİ",
                               raw={"id": "152"}, bm25_norm=1.0, token_set_ratio=97.0)]
    subunits = [
        ScoredCandidate(id="900", record_type="subunit", name="EGE TIP",
                        raw={"id": "900", "parent_id": "152"}, bm25_norm=0.9,
                        token_set_ratio=60.0),
        ScoredCandidate(id="901", record_type="subunit", name="GAZİ TIP",
                        raw={"id": "901", "parent_id": "999"}, bm25_norm=0.8,
                        token_set_ratio=95.0, exact_match=True, exact_match_text="gazi tip"),
    ]
    return ResolveResult(query="ege universitesi tip", decomposed=dq,
                         parents=parents, subunits=subunits)


class TestJudgeIntegration:
    def test_downgrades_instead_of_raising(self):
        """Bagli semada tutarsizlik uretilemez; onun yerine en guclu kanit baska
        parent'a isaret ediyorsa auto_match -> review INDIRGENIR (satir kaybolmaz)."""
        client = _Fake({"parent": {"verdict": "auto_match", "matched_id": "P1|EGE ÜNİVERSİTESİ"},
                        "unit_phrase": "tip",
                        "subunit": {"verdict": "auto_match", "matched_id": "S1|EGE TIP"}})
        out = judge(_resolve_result(), client, variant=V5)
        assert out.parent.verdict == "review"      # indirgendi
        assert out.subunit.verdict == "review"
        assert out.parent.matched_id == "152"      # kimlik KORUNUR
        assert out.subunit.matched_id == "900"

    def test_no_downgrade_without_bound_schema(self):
        """v4'te ayni durum zaten `_validate_ids`e takilir ya da normal akar -
        dedektor devreye GIRMEZ, iki kez cezalandirmayalim."""
        client = _Fake({"parent": {"verdict": "auto_match", "matched_id": "P1|EGE ÜNİVERSİTESİ"},
                        "unit_phrase": "tip",
                        "subunit": {"verdict": "auto_match", "matched_id": "S1|EGE TIP"}})
        out = judge(_resolve_result(), client, variant=V4)
        assert out.parent.verdict == "auto_match"

    def test_bound_schema_reaches_client(self):
        client = _Fake({"parent": {"verdict": "no_match", "matched_id": None},
                        "unit_phrase": None, "subunit": None})
        judge(_resolve_result(), client, variant=V5)
        assert "anyOf" in client.schema
        assert len(client.schema["anyOf"]) == 2  # no_match + 1 parent

    def test_cross_parent_still_rejected_when_unbound(self):
        """v4 (bagimsiz sema): tutarsiz cift HALA reddedilir - bu davranis
        bagli sema disinda korunuyor."""
        client = _Fake({"parent": {"verdict": "auto_match", "matched_id": "P1|EGE ÜNİVERSİTESİ"},
                        "unit_phrase": "tip",
                        "subunit": {"verdict": "auto_match", "matched_id": "S2|GAZİ TIP"}})
        with pytest.raises(JudgeValidationError, match="uyuşmazlığı"):
            judge(_resolve_result(), client, variant=V4)
