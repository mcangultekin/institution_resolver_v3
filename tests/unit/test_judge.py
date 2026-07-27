"""judge/ birim testleri - LLM'siz (sahte client), pydantic dogrulama + halusinasyon yakalama.

Gercek Ollama gerektirmez (varsayilan `pytest tests/unit` calismasinda hepsi
gecer). Canli model karsilastirmasi icin ayri, `@pytest.mark.llm` isaretli
testler dosyanin sonunda - Ollama calismiyorsa/model cekilmemisse KENDILIGINDEN
atlanir (skip), suit'i kirmaz.
"""

from __future__ import annotations

import json

import httpx
import pytest

from institution_resolver_v3.judge.candidates import build_candidate_views
from institution_resolver_v3.judge.client import OllamaClient
from institution_resolver_v3.judge.judge import JudgeValidationError, judge
from institution_resolver_v3.judge.prompt import build_prompt
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate


def _decomposed() -> DecomposedQuery:
    hyp = BoundaryHypothesis(
        institution_part="pécsi tudományegyetem",
        unit_part="anesztezi klinika",
        boundary_score=95.0,
        matched_parent_name="Pécsi Tudományegyetem",
        matched_parent_id="58062",
    )
    return DecomposedQuery(
        institution_part=hyp.institution_part,
        unit_part=hyp.unit_part,
        boundary_score=hyp.boundary_score,
        matched_parent_name=hyp.matched_parent_name,
        matched_parent_id=hyp.matched_parent_id,
        hypotheses=[hyp],
    )


def _result(subunits: list[ScoredCandidate] | None = None) -> ResolveResult:
    parents = [
        ScoredCandidate(
            id="58062",
            record_type="parent",
            name="Pécsi Tudományegyetem",
            raw={"id": "58062", "country": "HU", "city": "Pécs"},
            bm25_norm=1.0,
            cosine=0.9,
            token_set_ratio=95.0,
            qualifier_conflict=False,
        ),
    ]
    return ResolveResult(
        query="pécsi tudományegyetem anesztezi klinika",
        decomposed=_decomposed(),
        parents=parents,
        subunits=subunits or [],
    )


class _FakeClient:
    def __init__(self, response: str):
        self.response = response
        self.last_prompt: str | None = None

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        format_schema: dict | None = None,
    ) -> str:
        self.last_prompt = prompt
        self.last_format_schema = format_schema
        return self.response


class TestPrompt:
    def test_contains_raw_query_verbatim(self):
        result = _result()
        parents, subunits = build_candidate_views(result)
        prompt = build_prompt(result.query, result.decomposed, parents, subunits)
        assert result.query in prompt

    def test_no_preseg_unit_part_leaked(self):
        # unit_part (kural-tabanli "artik") prompt'a HIC girmemeli - ham metin ilkesi
        # (bkz. prompt.py modul docstring'i, docs/DURUM.md 2026-07-24 notlari).
        result = _result()
        parents, subunits = build_candidate_views(result)
        prompt = build_prompt(result.query, result.decomposed, parents, subunits)
        assert "anesztezi klinika" not in prompt.lower().replace(result.query.lower(), "")

    def test_cosine_not_shown_to_judge(self):
        # 2026-07-27: ham kosinüs hakeme GÖSTERİLMEZ. Ölçüldü ki e5-base
        # anizotropik - mutlak/göreli kosinüs yanıltıcı ranking sinyaliydi
        # (doğru eşleşme havuz-içi ort. 4. sırada). kNN retrieval'da KALIR;
        # bu yalnızca hakemin PROMPT görünümüyle ilgili (bkz. prompt.py docstring).
        result = _result()
        parents, subunits = build_candidate_views(result)
        prompt = build_prompt(result.query, result.decomposed, parents, subunits)
        assert "kosinüs" not in prompt.lower()

    def test_separate_decision_rule_present(self):
        result = _result()
        parents, subunits = build_candidate_views(result)
        prompt = build_prompt(result.query, result.decomposed, parents, subunits)
        assert "no_match" in prompt and "auto_match" in prompt

    def test_exact_match_shown_per_candidate(self):
        # 2026-07-24, kullanici talebi: tam-eslesme sinyali prompt'ta gorunmeli
        # (token_benzerlik=100'den AYRI bir kanit, bkz. prompt.py "TAM_EŞLEŞME NOTU").
        result = _result()
        result.parents[0].exact_match = True
        parents, subunits = build_candidate_views(result)
        prompt = build_prompt(result.query, result.decomposed, parents, subunits)
        assert "tam_eşleşme=EVET" in prompt


class TestCandidateViews:
    def test_subunit_inherits_country_city_from_parent(self):
        subunits = [
            ScoredCandidate(
                id="900",
                record_type="subunit",
                name="Aneszteziológiai Klinika",
                raw={
                    "parent_id": "58062",
                    "parent_name": "Pécsi Tudományegyetem",
                    "kind_label_raw": "klinika",
                },
                bm25_norm=0.8,
                cosine=0.7,
                token_set_ratio=70.0,
                qualifier_conflict=False,
            ),
        ]
        result = _result(subunits=subunits)
        _, s_views = build_candidate_views(result)
        assert s_views[0].country == "HU"
        assert s_views[0].city == "Pécs"
        assert s_views[0].parent_name == "Pécsi Tudományegyetem"
        assert s_views[0].kind_label == "klinika"

    def test_subunit_country_none_when_parent_not_in_pool(self):
        subunits = [
            ScoredCandidate(
                id="900",
                record_type="subunit",
                name="X",
                raw={"parent_id": "999"},
                bm25_norm=0.5,
                cosine=None,
                token_set_ratio=50.0,
                qualifier_conflict=False,
            ),
        ]
        result = ResolveResult(query="q", decomposed=_decomposed(), parents=[], subunits=subunits)
        _, s_views = build_candidate_views(result)
        assert s_views[0].country is None
        assert s_views[0].city is None

    def test_exact_match_propagated(self):
        result = _result()
        result.parents[0].exact_match = True
        p_views, _ = build_candidate_views(result)
        assert p_views[0].exact_match is True


class TestCandidateTrimming:
    """2026-07-24, canli bulgu ("Ege University" ornegi): uzun/gurultulu aday
    listesi (18 parent) E2B'yi yaniltiyordu, 5'e kirpilinca dogru cevabi
    buldu. `build_candidate_views` artik hakeme giden goruntuyu kirpar -
    `resolve()`'un kendi ic havuzu ETKILENMEZ (bkz. candidates.py docstring'i)."""

    def _many_parents(self, n: int, exact_ids: set[str] | None = None) -> list[ScoredCandidate]:
        exact_ids = exact_ids or set()
        return [
            ScoredCandidate(
                id=str(i),
                record_type="parent",
                name=f"Kurum {i}",
                raw={},
                bm25_norm=1.0 - i * 0.01,
                cosine=None,
                token_set_ratio=50.0,
                qualifier_conflict=False,
                exact_match=str(i) in exact_ids,
            )
            for i in range(n)
        ]

    def test_trims_to_max_candidates(self):
        result = ResolveResult(
            query="q", decomposed=_decomposed(), parents=self._many_parents(18), subunits=[]
        )
        p_views, _ = build_candidate_views(result, max_candidates=8)
        assert len(p_views) == 8

    def test_exact_match_survives_trim_even_if_late_in_list(self):
        # gercek "Ege" ornegindeki gibi: dogru cevap ONDE olsa bile, guvenlik
        # icin - SONDA da olsa exact_match asla disari atilmamali.
        parents = self._many_parents(18, exact_ids={"17"})  # son sirada
        result = ResolveResult(query="q", decomposed=_decomposed(), parents=parents, subunits=[])
        p_views, _ = build_candidate_views(result, max_candidates=8)
        assert any(v.id == "17" for v in p_views)

    def test_no_trim_when_pool_already_small(self):
        result = ResolveResult(
            query="q", decomposed=_decomposed(), parents=self._many_parents(3), subunits=[]
        )
        p_views, _ = build_candidate_views(result, max_candidates=8)
        assert len(p_views) == 3


class TestJudgeHappyPath:
    def test_parent_matched_subunit_none_when_not_requested(self):
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": "58062"},
            "subunit": None,
        }
        client = _FakeClient(json.dumps(payload))
        out = judge(_result(), client)
        assert out.parent.verdict == "auto_match"
        assert out.parent.matched_id == "58062"
        assert out.subunit is None

    def test_parent_auto_subunit_no_match_is_valid_combo(self):
        # Pecs senaryosu: kurum dogru, birim korpusta yok - sorgunun TAMAMI
        # no_match SAYILMAZ, sadece subunit du?er (bkz. docs/DURUM.md).
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": "58062"},
            "subunit": {"verdict": "no_match", "matched_id": None},
        }
        client = _FakeClient(json.dumps(payload))
        out = judge(_result(), client)
        assert out.parent.verdict == "auto_match"
        assert out.subunit.verdict == "no_match"
        assert out.subunit.matched_id is None


class TestJudgeValidation:
    def test_invalid_json_raises(self):
        client = _FakeClient("bu JSON degil, duz metin")
        with pytest.raises(JudgeValidationError):
            judge(_result(), client)

    def test_schema_violation_raises(self):
        # auto_match verdict'inde matched_id eksik -> pydantic validator hata versin.
        payload = {"parent": {"verdict": "auto_match", "matched_id": None}}
        client = _FakeClient(json.dumps(payload))
        with pytest.raises(JudgeValidationError):
            judge(_result(), client)

    def test_hallucinated_parent_id_raises(self):
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": "UYDURMA_ID"},
            "subunit": None,
        }
        client = _FakeClient(json.dumps(payload))
        with pytest.raises(JudgeValidationError):
            judge(_result(), client)

    def test_hallucinated_subunit_id_raises(self):
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": "58062"},
            "subunit": {"verdict": "auto_match", "matched_id": "HAYALET_ID"},
        }
        client = _FakeClient(json.dumps(payload))
        with pytest.raises(JudgeValidationError):
            judge(_result(), client)


class TestMatchedIdNormalization:
    """50-sorgu E2B/E4B canli karsilastirmasinda gozlemlendi (2026-07-24):
    E4B rakam-dizgesi id'leri (ör. "101") SIK SIK JSON sayi olarak donduruyor,
    "eslesme yok" da bazen JSON null yerine LITERAL "null" dizgesi oluyor -
    bunlar model hatasi degil, sema kati davranirsa YANLIS ZEMINDE reddedilirdi."""

    def test_int_matched_id_coerced_to_str(self):
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": 58062},
            "subunit": None,
        }
        client = _FakeClient(json.dumps(payload))
        out = judge(_result(), client)
        assert out.parent.matched_id == "58062"

    def test_literal_null_string_normalized_to_none(self):
        payload = {
            "parent": {"verdict": "auto_match", "matched_id": "58062"},
            "subunit": {"verdict": "no_match", "matched_id": "null"},
        }
        client = _FakeClient(json.dumps(payload))
        out = judge(_result(), client)
        assert out.subunit.matched_id is None


def _ollama_reachable(host: str) -> bool:
    try:
        httpx.get(f"{host}/api/version", timeout=1.0)
        return True
    except httpx.HTTPError:
        return False


@pytest.mark.llm
class TestLiveOllama:
    """Canli cagri: gemma4:e2b (2026-07-24 karar - E4B/50-sorgu karsilastirmasi
    sonrasi E2B secildi, bkz. docs/DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md;
    E4B yerel Ollama'dan silindi). `pytest -m llm` ile calistir.

    Ollama ayakta degilse ya da model cekilmemisse SKIP olur - varsayilan
    suit'i (tests/unit -q) kirmaz.
    """

    HOST = "http://localhost:11434"

    def test_live_judge_call(self):
        if not _ollama_reachable(self.HOST):
            pytest.skip("Ollama calismiyor (localhost:11434)")
        client = OllamaClient(model="gemma4:e2b", host=self.HOST)
        try:
            out = judge(_result(), client)
        except Exception as exc:  # model cekilmemis, timeout vb. - test ortami eksik
            pytest.skip(f"canli cagri basarisiz: {exc}")
        assert out.parent.verdict in {"auto_match", "review", "ambiguous", "no_match"}
