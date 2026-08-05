"""Parent-only hakem cikti semasi - tek alan.

`ParentDecision` cekirdekten (judge/schema.py) IMPORT edilir, kopyalanmaz:
verdict/matched_id capraz-alan tutarliligi ("no_match dedi ama id verdi" ya da
"auto_match dedi ama id vermedi" -> reddedilir) ve girdi normalizasyonu (id'yi
JSON SAYI olarak donduren model, "null"/"none" DIZGESI donduren model) orada
zaten kanit-yuklu bicimde cozulmus.

Cekirdek `JudgeResult`ten farklar:
- `subunit` alani YOK.
- `unit_phrase` alani YOK: o, cok-seviyeli sorgularda subunit secimini dogru
  seviyeye cekmek icin konmus bir dikkat cipasiydi (2026-07-24 Ege/Geriatri
  bulgusu). Parent-only'de secilecek subunit olmadigi icin islevsiz - ve
  uretilmemesi token/sure kazandirir.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from institution_resolver_v3.judge.schema import ParentDecision, Verdict

__all__ = ["ParentDecision", "ParentOnlyResult", "Verdict"]


class ParentOnlyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent: ParentDecision
