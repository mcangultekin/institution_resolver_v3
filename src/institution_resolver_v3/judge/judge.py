"""F4 orkestrasyon: resolve() sonucunu al, prompt kur, LLM cagir, ciktiyi dogrula.

Dogrulayici (halusinasyon yakalama): LLM'in dondurdugu `matched_id` GERCEKTEN
aday havuzunda (parents/subunits listesinde) olmali - kucuk model (E2B/E4B)
sema disi/uydurma id verebilir; bu TEK BASINA guven kaybi degil ama SESSIZCE
GECILMEZ (bkz. docs/DURUM.md F4 model secimi notlari - dogruluk riski, model
kucultmenin maliyet kazancini nasil etkiledigi henuz olculmedi).

Hatalar (JSON parse, sema disi cikti, id-halusinasyonu, LLM baglanti hatasi)
burada YUTULMAZ - cagiran taraf (F5 batch, ileride) retry/no_match'e dusurme
kararini kendisi verir. "Yetki asimetrisi" (LLM auto'ya terfi edebilir mi)
docs/DURUM.md'de HALA ACIK bir karar - bu modul burada VARSAYIM YAPMAZ, ham
JudgeResult'i oldugu gibi doner.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from institution_resolver_v3.judge.candidates import CandidateView, build_candidate_views
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.judge.prompt import build_prompt
from institution_resolver_v3.judge.schema import JudgeResult
from institution_resolver_v3.retrieve.resolve import ResolveResult


class JudgeValidationError(RuntimeError):
    """LLM ciktisi sema disi ya da aday havuzunda olmayan bir id iceriyor.

    Mesaj, pydantic'in teknik `ValidationError` metnini (type=value_error,
    input_value=... gibi gelistirici-yonelimli jargon) DEGIL, sade Turkce bir
    aciklama tasir - bkz. `_format_validation_error` (2026-07-24, kullanici
    "anlasilir hata mesaji" talebi)."""


def _format_validation_error(exc: ValidationError) -> str:
    """Pydantic `ValidationError.errors()`'u okunabilir tek satira cevirir.

    `exc.errors()` her ihlal icin {'loc': (alan yolu), 'msg': mesaj, ...} doner.
    Kendi `model_validator`larimizin fırlattigi ValueError'lar pydantic
    tarafindan "Value error, <mesajimiz>" seklinde on-ekleniyor - o on-ek
    kullaniciya anlamsiz oldugu icin siliniyor.
    """
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "cikti"
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        parts.append(f"[{loc}] {msg}")
    return " ; ".join(parts)


def _validate_ids(
    result: JudgeResult, parents: list[CandidateView], subunits: list[CandidateView]
) -> None:
    parent_ids = {c.id for c in parents}
    subunit_ids = {c.id for c in subunits}
    if result.parent.matched_id is not None and result.parent.matched_id not in parent_ids:
        raise JudgeValidationError(
            f"Hakem, kurum (parent) için aday listesinde OLMAYAN bir id döndürdü: "
            f"{result.parent.matched_id!r} (muhtemelen uydurma/halüsinasyon)."
        )
    if (
        result.subunit is not None
        and result.subunit.matched_id is not None
        and result.subunit.matched_id not in subunit_ids
    ):
        raise JudgeValidationError(
            f"Hakem, alt-birim (subunit) için aday listesinde OLMAYAN bir id döndürdü: "
            f"{result.subunit.matched_id!r} (muhtemelen uydurma/halüsinasyon)."
        )


def judge(resolve_result: ResolveResult, client: LlmClient) -> JudgeResult:
    """resolve() ciktisini hakeme sorar, dogrulanmis `JudgeResult` doner."""
    parents, subunits = build_candidate_views(resolve_result)
    prompt = build_prompt(resolve_result.query, resolve_result.decomposed, parents, subunits)
    raw = client.generate(prompt)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JudgeValidationError(
            f"Hakem geçerli bir JSON döndürmedi (metin çıktısı bozuk): {exc}. "
            f"Ham çıktının başı: {raw[:200]!r}"
        ) from exc

    try:
        result = JudgeResult.model_validate(payload)
    except ValidationError as exc:
        raise JudgeValidationError(
            f"Hakemin cevabı çelişkili/eksik: {_format_validation_error(exc)}"
        ) from exc

    _validate_ids(result, parents, subunits)
    return result
