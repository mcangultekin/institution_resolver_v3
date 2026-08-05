"""parent_only/ birim testleri - ES'siz, LLM'siz (sahte search_fn / sahte client).

Iki sinif test var:
1. Parent-only yolun KENDI davranisi (gate kovalari, 3 mod, batch kolonlari).
2. **Cekirdekle esdegerlik**: ayni aday havuzunda `parent_only.gate_parent()` ile
   cekirdek `gate.gate().parent` AYNI karari vermeli - bu modun temel iddiasi
   ("parent karari degismiyor, sadece subunit hesaplanmiyor") testle cakilir.
"""

from __future__ import annotations

import csv
import json

import pytest

from institution_resolver_v3.gate.gate import gate as core_gate
from institution_resolver_v3.judge.judge import JudgeValidationError
from institution_resolver_v3.parent_only.batch import FIELDNAMES, run_parent_batch
from institution_resolver_v3.parent_only.decide import decide_parent
from institution_resolver_v3.parent_only.gate import gate_parent
from institution_resolver_v3.parent_only.judge import (
    build_parent_format_schema,
    judge_parent,
)
from institution_resolver_v3.parent_only.resolve import resolve_parent
from institution_resolver_v3.retrieve.decompose import BoundaryHypothesis, DecomposedQuery
from institution_resolver_v3.retrieve.resolve import ResolveResult, ScoredCandidate

_CFG = {"gate": {"garbage_lexical_floor": 0.55}}


def _cand(
    id: str,
    name: str,
    *,
    tsr: float = 0.0,
    exact_text: str | None = None,
    conflict: bool = False,
) -> ScoredCandidate:
    return ScoredCandidate(
        id=id,
        record_type="parent",
        name=name,
        raw={"id": id, "record_type": "parent", "name": name},
        bm25_norm=0.9,
        cosine=None,
        token_set_ratio=tsr,
        qualifier_conflict=conflict,
        exact_match=exact_text is not None,
        exact_match_text=exact_text,
    )


def _result(parents: list[ScoredCandidate], *, query="ege universitesi", part=None) -> ResolveResult:
    part = part if part is not None else query
    dq = DecomposedQuery(
        institution_part=part,
        unit_part="",
        boundary_score=95.0,
        matched_parent_name=None,
        matched_parent_id=None,
        hypotheses=[BoundaryHypothesis(part, "", 95.0, None, None)],
    )
    return ResolveResult(query=query, decomposed=dq, parents=parents, subunits=[])


# --------------------------------------------------------------------- gate
def test_tek_guclu_exact_auto_match():
    r = _result([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")])
    g = gate_parent(r, config=_CFG)
    assert (g.verdict, g.matched_id) == ("auto_match", "1")


def test_coklu_exact_ambiguous_span_farkina_bakilmaz():
    """Parent'ta HERHANGI ikinci exact auto'yu engeller (any_rival_blocks_auto=True)."""
    r = _result(
        [
            _cand("1", "İSTANBUL ÜNİVERSİTESİ-CERRAHPAŞA", tsr=95.0,
                  exact_text="istanbul universitesi cerrahpasa"),
            _cand("2", "İSTANBUL ÜNİVERSİTESİ", tsr=90.0, exact_text="istanbul universitesi"),
        ],
        query="istanbul universitesi cerrahpasa tip fakultesi",
        part="istanbul universitesi cerrahpasa",
    )
    g = gate_parent(r, config=_CFG)
    assert g.verdict == "ambiguous"
    assert g.signals["reason"] == "coklu_exact_herhangi"


def test_exact_yoksa_taban_alti_no_match():
    r = _result([_cand("1", "ALAKASIZ KURUM", tsr=20.0)])
    assert gate_parent(r, config=_CFG).verdict == "no_match"


def test_exact_yoksa_taban_ustu_review():
    r = _result([_cand("1", "BOZOK ÜNİVERSİTESİ", tsr=88.0)])
    g = gate_parent(r, config=_CFG)
    assert (g.verdict, g.signals["reason"]) == ("review", "exact_yok")


def test_bos_havuz_no_match():
    assert gate_parent(_result([]), config=_CFG).verdict == "no_match"


def test_tek_token_exact_auto_vermez():
    """span>=2 kurali (jenerik tek-token korumasi) parent-only'de de gecerli."""
    r = _result([_cand("1", "HASTANESİ", tsr=100.0, exact_text="hastanesi")])
    assert gate_parent(r, config=_CFG).verdict != "auto_match"


# ------------------------------------------- cekirdekle esdegerlik (temel iddia)
@pytest.mark.parametrize(
    "parents",
    [
        [_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")],
        [_cand("1", "A ÜNİVERSİTESİ", tsr=95.0, exact_text="a universitesi"),
         _cand("2", "A ÜNİVERSİTESİ B", tsr=93.0, exact_text="a universitesi b")],
        [_cand("1", "ALAKASIZ", tsr=20.0)],
        [_cand("1", "YAKIN AMA EXACT DEGIL", tsr=80.0)],
        [],
    ],
)
def test_cekirdek_gate_ile_ayni_parent_karari(parents):
    """Bu modun temel iddiasi: parent karari cekirdektekiyle BIREBIR ayni."""
    r = _result(parents)
    assert gate_parent(r, config=_CFG) == core_gate(r, config=_CFG).parent


# ------------------------------------------------------------------- resolve
def test_resolve_parent_subunit_aramaz():
    """Sahte arama fn'i subunit icin HIC cagrilmamali; subunits daima bos."""
    seen: list[str] = []

    def fake_search(text, record_type, *, extra_filters=None, size=50):
        seen.append(record_type)
        return [{"id": "1", "record_type": "parent", "name": "EGE ÜNİVERSİTESİ",
                 "score": 10.0, "aliases": []}]

    def fake_knn(text, record_type, *, extra_filters=None, size=50):
        seen.append(record_type)
        return []

    res = resolve_parent("ege universitesi", size=3, search_fn=fake_search, search_knn_fn=fake_knn)
    assert res.subunits == []
    assert "subunit" not in seen
    assert res.parents and res.parents[0].id == "1"


def test_resolve_parent_kosinus_geri_doldurmaz():
    """kNN listesine girmeyen aday icin mget/encode yolu HIC acilmaz -> cosine None.

    (kNN'de gorunen adaylar kosinusu ES skorundan almaya devam eder; burada sahte
    kNN bos donduugu icin geri-doldurma olsaydi mget denenirdi.)"""
    def fake_search(text, record_type, *, extra_filters=None, size=50):
        return [{"id": "1", "record_type": "parent", "name": "EGE ÜNİVERSİTESİ",
                 "score": 10.0, "aliases": []}]

    res = resolve_parent("ege universitesi", search_fn=fake_search,
                         search_knn_fn=lambda *a, **k: [])
    assert all(c.cosine is None for c in res.parents)


def test_max_span_uzun_pencereleri_atlar():
    """max_span verilince aranan metinlerin hicbiri sinirdan uzun olmamali."""
    aranan: list[str] = []

    def fake_search(text, record_type, *, extra_filters=None, size=50):
        return [{"id": "1", "record_type": "parent", "name": "X", "score": 1.0, "aliases": []}]

    def fake_many(texts, record_type):
        aranan.extend(texts)
        return [[] for _ in texts]

    resolve_parent(
        "bir iki uc dort bes alti",
        search_fn=fake_search,
        search_knn_fn=lambda *a, **k: [],
        decompose_search_fn=lambda t, rt: fake_many([t], rt)[0],
        max_span=2,
    )
    assert aranan, "span aramasi hic yapilmadi"
    assert max(len(t.split()) for t in aranan) <= 2


# --------------------------------------------------------------------- judge
class _FakeClient:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def generate(self, prompt, *, temperature=0.0, format_schema=None):
        self.prompts.append(prompt)
        self.schemas.append(format_schema)
        return self.response


def test_judge_parent_etiketi_gercek_ide_cevirir():
    r = _result([_cand("77", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")])
    client = _FakeClient(json.dumps({"parent": {"verdict": "auto_match",
                                                "matched_id": "P1|EGE ÜNİVERSİTESİ"}}))
    out = judge_parent(r, client)
    assert (out.parent.verdict, out.parent.matched_id) == ("auto_match", "77")
    # prompt'ta subunit bolumu OLMAMALI
    assert "ALT-BİRİM" not in client.prompts[0]


def test_judge_parent_semasi_tek_alan():
    r = _result([_cand("77", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")])
    client = _FakeClient(json.dumps({"parent": {"verdict": "no_match", "matched_id": None}}))
    judge_parent(r, client)
    schema = client.schemas[0]
    assert list(schema["properties"]) == ["parent"]
    assert "subunit" not in schema["properties"] and "unit_phrase" not in schema["properties"]


def test_judge_parent_halusinasyon_id_reddedilir():
    r = _result([_cand("77", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")])
    client = _FakeClient(json.dumps({"parent": {"verdict": "auto_match", "matched_id": "9999"}}))
    with pytest.raises(JudgeValidationError):
        judge_parent(r, client)


def test_judge_parent_celiskili_cikti_reddedilir():
    """no_match + id ya da auto_match + id yok -> sema hatasi (cekirdek validator)."""
    r = _result([_cand("77", "EGE ÜNİVERSİTESİ", tsr=100.0, exact_text="ege universitesi")])
    client = _FakeClient(json.dumps({"parent": {"verdict": "auto_match", "matched_id": None}}))
    with pytest.raises(JudgeValidationError):
        judge_parent(r, client)


def test_bos_havuzda_sema_yalniz_no_match_birakir():
    schema = build_parent_format_schema([])
    assert schema["properties"]["parent"]["properties"]["verdict"]["const"] == "no_match"


# -------------------------------------------------------------------- decide
def _stub_resolve(parents):
    return lambda q, *, size=5, max_span=None: _result(parents, query=q)


# Testler ES'e CIKMAMALI: `decide_parent`in varsayilan `count_fn`i canli msearch
# yapar. Her cagriya acikca enjekte edilir (bkz. jenerik-ad korumasi testleri).
def _no_counts(names):
    return {}


def test_mode_gate_llm_cagirmaz():
    client = _FakeClient("PATLARDI")
    d = decide_parent(
        "ege universitesi", client, mode="gate", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0,
                                        exact_text="ege universitesi")]),
    )
    assert (d.decided_by, d.verdict, d.judge) == ("gate", "auto_match", None)
    assert client.prompts == []


def test_mode_gate_client_olmadan_calisir():
    d = decide_parent(
        "ege universitesi", None, mode="gate", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0,
                                        exact_text="ege universitesi")]),
    )
    assert d.decided_by == "gate"


def test_mode_hybrid_auto_ise_llm_cagirmaz():
    client = _FakeClient("PATLARDI")
    d = decide_parent(
        "ege universitesi", client, mode="hybrid", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0,
                                        exact_text="ege universitesi")]),
    )
    assert d.decided_by == "gate" and client.prompts == []


def test_mode_hybrid_auto_degilse_hakeme_devreder():
    client = _FakeClient(json.dumps({"parent": {"verdict": "review", "matched_id": "P1|BOZOK"}}))
    d = decide_parent(
        "bozok univesitesi", client, mode="hybrid", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "BOZOK", tsr=88.0)]),
    )
    assert (d.decided_by, d.verdict, d.matched_id) == ("judge", "review", "1")
    assert d.gate.verdict == "review"  # gate karari denetim icin korunur


def test_mode_llm_auto_olsa_bile_hakeme_gider():
    client = _FakeClient(json.dumps({"parent": {"verdict": "no_match", "matched_id": None}}))
    d = decide_parent(
        "ege universitesi", client, mode="llm", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0,
                                        exact_text="ege universitesi")]),
    )
    assert (d.decided_by, d.verdict) == ("judge", "no_match")
    assert d.gate.verdict == "auto_match"  # gate ne demisti - kayitli


def test_gecersiz_mode_hata():
    with pytest.raises(ValueError):
        decide_parent("x", None, mode="yok")  # type: ignore[arg-type]


def test_gate_disi_mod_clientsiz_hata():
    with pytest.raises(ValueError):
        decide_parent("x", None, mode="hybrid")


# --------------------------------------------------------------------- batch
def test_batch_csv_kolonlari_ve_satirlari(tmp_path):
    out = tmp_path / "sonuc.csv"
    summary = run_parent_batch(
        ["ege universitesi", "gazi universitesi"],
        out,
        mode="gate",
        decide_fn=lambda q, c, *, mode, size, max_span: decide_parent(
            q, None, mode="gate", config=_CFG, count_fn=_no_counts,
            resolve_fn=_stub_resolve([_cand("1", "EGE ÜNİVERSİTESİ", tsr=100.0,
                                            exact_text="ege universitesi")]),
        ),
    )
    assert summary["ok"] == 2 and summary["error"] == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [*rows[0]] == FIELDNAMES
    assert rows[0]["verdict"] == "auto_match" and rows[0]["decided_by"] == "gate"
    assert rows[0]["mode"] == "gate"
    assert json.loads(rows[0]["result_json"])["matched_id"] == "1"


def test_batch_satir_hatasi_izole_edilir(tmp_path):
    """Bir sorgu patlarsa batch devam etmeli, satir 'error' olarak yazilmali."""
    def boom(q, c, *, mode, size, max_span):
        if "patla" in q:
            raise RuntimeError("test hatasi")
        return decide_parent(
            q, None, mode="gate", config=_CFG, count_fn=_no_counts,
            resolve_fn=_stub_resolve([_cand("1", "X", tsr=100.0, exact_text="x y")]),
        )

    out = tmp_path / "s.csv"
    summary = run_parent_batch(["iyi", "patla", "iyi2"], out, mode="gate", decide_fn=boom)
    assert summary["ok"] == 2 and summary["error"] == 1
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    err = [r for r in rows if r["status"] == "error"][0]
    assert "test hatasi" in err["error"]


def test_batch_resume_yapilan_satirlari_atlar(tmp_path):
    out = tmp_path / "s.csv"
    fn = lambda q, c, *, mode, size, max_span: decide_parent(  # noqa: E731
        q, None, mode="gate", config=_CFG, count_fn=_no_counts,
        resolve_fn=_stub_resolve([_cand("1", "X", tsr=100.0, exact_text="x y")]),
    )
    run_parent_batch(["a", "b"], out, mode="gate", decide_fn=fn)
    summary = run_parent_batch(["a", "b", "c"], out, mode="gate", decide_fn=fn, resume=True)
    assert summary["skipped"] == 2 and summary["ok"] == 1
    assert len(list(csv.DictReader(out.open(encoding="utf-8")))) == 3


# ------------------------------------------------- jenerik-ad korumasi (G1 + b)
_GCFG = {"gate": {"garbage_lexical_floor": 0.55}, "parent_only": {"generic_name_threshold": 3}}


def _generic_result():
    """Tek guclu exact -> normalde auto_match olurdu."""
    return _result(
        [_cand("1", "State Hospital", tsr=100.0, exact_text="state hospital")],
        query="gaziantep sehitkamil state hospital",
        part="gaziantep sehitkamil state hospital",
    )


def test_jenerik_ad_auto_yerine_review_verir():
    """Esigi asan aday auto olamaz - ama BLOKLANMAZ, oneri korunur (yonlendirme)."""
    g = gate_parent(_generic_result(), config=_GCFG, name_counts={"State Hospital": 20})
    assert g.verdict == "review"
    assert g.matched_id == "1", "yonlendirici: id oneri olarak korunmali"
    assert g.signals["reason"] == "jenerik_ad"
    assert g.signals["capped_from"] == "auto_match"
    assert g.signals["name_containment"] == 20


def test_jenerik_ad_esik_altinda_auto_kalir():
    g = gate_parent(_generic_result(), config=_GCFG, name_counts={"State Hospital": 2})
    assert g.verdict == "auto_match"


def test_sayilar_verilmezse_koruma_calismaz():
    """name_counts yoksa (ES erisilemedi vb.) davranis eski haliyle ayni."""
    assert gate_parent(_generic_result(), config=_GCFG).verdict == "auto_match"
    assert gate_parent(_generic_result(), config=_GCFG, name_counts={}).verdict == "auto_match"


def test_esik_sifirsa_koruma_kapali():
    cfg = {**_GCFG, "parent_only": {"generic_name_threshold": 0}}
    g = gate_parent(_generic_result(), config=cfg, name_counts={"State Hospital": 999})
    assert g.verdict == "auto_match"


def test_koruma_auto_disindaki_kararlara_dokunmaz():
    r = _result([_cand("1", "BOZOK ÜNİVERSİTESİ", tsr=88.0)])  # exact yok -> review
    g = gate_parent(r, config=_GCFG, name_counts={"BOZOK ÜNİVERSİTESİ": 999})
    assert (g.verdict, g.signals["reason"]) == ("review", "exact_yok")


def test_hibrit_modda_jenerik_ad_hakeme_yonlendirir():
    """G1'in asil amaci: gate'in supheli auto'su LLM'e dusssun."""
    client = _FakeClient(json.dumps({"parent": {"verdict": "no_match", "matched_id": None}}))
    d = decide_parent(
        "gaziantep sehitkamil state hospital", client, mode="hybrid", config=_GCFG,
        count_fn=lambda names: {"State Hospital": 20},
        resolve_fn=lambda q, *, size=5, max_span=None: _generic_result(),
    )
    assert d.decided_by == "judge", "jenerik ad hakeme yonlendirilmeliydi"
    assert d.gate.signals["reason"] == "jenerik_ad"


def test_prompt_ayirt_edicilik_satirini_gosterir():
    from institution_resolver_v3.parent_only.prompt import build_parent_prompt
    from institution_resolver_v3.judge.candidates import build_candidate_views

    views, _ = build_candidate_views(_generic_result())
    p_yuksek = build_parent_prompt("q", _generic_result().decomposed, views, {"State Hospital": 0})
    p_dusuk = build_parent_prompt("q", _generic_result().decomposed, views, {"State Hospital": 20})
    assert "başka hiçbir kurumun adının içinde geçmiyor" in p_yuksek
    assert "20 başka kurumun adının içinde geçiyor" in p_dusuk
    # sayilar verilmezse satir HIC eklenmez (eski prompt aynen)
    assert "içinde geç" not in build_parent_prompt("q", _generic_result().decomposed, views)


def test_judge_sayilari_prompta_gecirir():
    r = _result([_cand("77", "State Hospital", tsr=100.0, exact_text="state hospital")])
    client = _FakeClient(json.dumps({"parent": {"verdict": "review", "matched_id": "P1|X"}}))
    judge_parent(r, client, name_counts={"State Hospital": 20})
    assert "20 başka kurumun adının içinde geçiyor" in client.prompts[0]
