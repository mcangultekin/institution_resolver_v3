"""Parent-only hakem orkestrasyonu: aday paketle, prompt kur, LLM cagir, dogrula.

Cekirdek `judge/judge.py`den IMPORT edilenler (kopyalanmayanlar) ve nedenleri:
- `_decision_schema`: verdict/matched_id'yi TEK bir secime kilitleyen kisitli
  sema (ya "eslesme yok + id bos" ya da "su id + su karar") - celiskili cikti
  URETIM asamasinda imkansiz hale gelir.
- `_choice`: sema enum degerini "etiket|ad (diger_ad)" olarak kurar; secim
  boylece soyut bir id yerine ismin semantigine kilitlenir (2026-07-24
  Gazi/Cardiology bulgusu).
- `_label_views`: gercek katalog id'lerini kisa sentetik etiketlerle (P1, P2..)
  degistirir - kucuk model uzun rakamsal id'leri karistiriyordu. Etiket disari
  SIZMAZ, `_to_real` ile gercek id'ye cevrilir.
- `JudgeValidationError`: ayni hata tipi (jenerik mesaj + `debug` ayrinti).

Farklar: tek alanli sema; `_validate_ids`in parent/subunit capraz kontrolu YOK
(subunit yok), yalniz halusinasyon-id kontrolu kaldi.

Hatalar burada YUTULMAZ - cagiran taraf (decide/batch) retry/no_match'e dusurme
kararini kendisi verir (cekirdekteki ayni ilke).
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from institution_resolver_v3.judge.candidates import CandidateView, build_candidate_views
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.judge.judge import (
    JudgeValidationError,
    _choice,
    _decision_schema,
    _format_validation_error,
    _label_views,
)
from institution_resolver_v3.parent_only.config import max_candidates as _max_candidates
from institution_resolver_v3.parent_only.prompt import build_parent_prompt
from institution_resolver_v3.parent_only.schema import ParentOnlyResult
from institution_resolver_v3.retrieve.resolve import ResolveResult


def build_parent_format_schema(parents: list[CandidateView]) -> dict:
    """Ollama kisitli-uretim semasi: `ParentOnlyResult`in aynasi + aday enum'u."""
    return {
        "type": "object",
        "properties": {"parent": _decision_schema([_choice(c) for c in parents])},
        "required": ["parent"],
    }


def _validate_parent_id(result: ParentOnlyResult, parents: list[CandidateView]) -> None:
    """Katalog-karsi dogrulama: hakemin verdigi id GERCEKTEN aday havuzunda mi.

    Sema-kisitli uretimde bu pratikte imkansiz; yine de tutuluyor cunku sema
    destegi OLMAYAN bir client enjekte edilirse (Protocol geregi mumkun) tek
    koruma budur - cekirdekteki "kusak + pantolon askisi" gerekcesi."""
    if result.parent.matched_id is None:
        return
    if result.parent.matched_id not in {c.id for c in parents}:
        raise JudgeValidationError(
            "Hakem geçersiz bir cevap verdi (bilinmeyen kurum kaydı).",
            debug=(
                f"parent.matched_id={result.parent.matched_id!r} aday havuzunda yok "
                "(halüsinasyon)."
            ),
        )


def judge_parent(
    resolve_result: ResolveResult,
    client: LlmClient,
    *,
    max_candidates: int | None = None,
    config: dict | None = None,
    name_counts: dict[str, int] | None = None,
) -> ParentOnlyResult:
    """`resolve_parent()` ciktisini hakeme sorar, dogrulanmis sonucu doner.

    `name_counts` (bkz. genericity.py) verilirse her aday satirinda adin ayirt
    ediciligi de gosterilir - olculdu: jenerik kayda yanlis auto veren 11 vakanin
    4 yerine 7'si duzeliyor, 15 saglam karar bozulmuyor."""
    mc = max_candidates if max_candidates is not None else _max_candidates(config)
    parents, _ = build_candidate_views(resolve_result, max_candidates=mc)
    parents_lbl, p_map = _label_views(parents, "P")

    prompt = build_parent_prompt(
        resolve_result.query, resolve_result.decomposed, parents_lbl, name_counts
    )
    raw = client.generate(prompt, format_schema=build_parent_format_schema(parents_lbl))

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JudgeValidationError(
            "Hakem geçerli bir yanıt döndürmedi (biçim hatası).",
            debug=f"JSON parse hatası: {exc}. Ham çıktının başı: {raw[:200]!r}",
        ) from exc

    try:
        result = ParentOnlyResult.model_validate(payload)
    except ValidationError as exc:
        raise JudgeValidationError(
            "Hakemin cevabı şemaya uymuyor (çelişkili/eksik alan).",
            debug=_format_validation_error(exc),
        ) from exc

    # "etiket|ad" -> gercek id. Haritada olmayan deger oldugu gibi birakilir;
    # `_validate_parent_id` onu yakalar (sahte/test client'lari gercek id de
    # dondurebilir, o yol da calismali) - cekirdekteki ayni sozlesme.
    if result.parent.matched_id is not None:
        label = result.parent.matched_id.split("|", 1)[0]
        result.parent.matched_id = p_map.get(label, result.parent.matched_id)

    _validate_parent_id(result, parents)
    return result
