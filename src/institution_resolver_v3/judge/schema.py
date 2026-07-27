"""Hakem cikti semasi - F4 (bkz. docs/DURUM.md, 2026-07-24 Pecs ornegi tasarim notlari).

Karar PARENT ve SUBUNIT icin AYRI verilir: `parent=auto_match + subunit=no_match`
birinci sinif, gecerli bir sonuctur (kirli/yabanci sorgularda muhtemelen en
yaygin dogru cevap - ör. Pecs: parent dogru, subunit korpusta yok). Sorguda
zaten bir birim ifadesi YOKSA `subunit` alani `None` kalir - bu, "istendi ama
bulunamadi" (`SubunitDecision(verdict="no_match")`) ile KARISTIRILMAMALI, iki
ayri durumdur (hakem bu ayrimi ham metinden kendisi cikarir).

`matched_id`/`verdict` tutarliligi burada (pydantic validator ile) zorlanir -
kucuk modelin sema disi/celiskili cikti verme riski var (bkz. F4 model secimi
notlari); id'nin GERCEKTEN aday havuzunda olup olmadigi (halusinasyon) burada
DEGIL `judge.py`de kontrol edilir (bu modul aday havuzunu bilmez, saf sema).

`reasoning` alani KALDIRILDI (2026-07-24, kullanici karari): sade
"parent=X, subunit=Y" yeterli, gerekce cumlesi hem gereksiz hem de LLM'in
urettigi token sayisini (dolayisiyla suresini) ciddi arttiriyordu (~200 token
-> hedef ~10-20 token, bkz. docs/DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md
performans notlari). review/ambiguous durumlarda "neden emin degil" bilgisi
kaybolur - bu bilinen bir odun, geri getirilebilir (decide/ katmaninda ihtiyac
cikarsa).

`matched_id` girdi-normalizasyonu (2026-07-24, 50-sorgu E2B/E4B karsilastirmasi
canli olcumu): katalog id'lerimiz rakam-dizgesi oldugu icin (ör. "101", "58062")
E4B bunlari SIK SIK JSON STRING degil JSON SAYI olarak donduruyor (`matched_id: 101`)
- bu bir model "hatasi" degil, bizim sema katiligimiz; int gelirse str()'e cevrilir.
Ayni sekilde bazi cikislarda "eslesme yok" JSON `null` yerine LITERAL "null"/"none"
DIZGESI olarak geliyor - bu da None'a normalize edilir (aksi halde havuzda-olmayan-id
halusinasyonu sanilirdi, bkz. judge.py _validate_ids). Asil sema-disi durumlar (ör.
verdict alaninin kendisine "null" yazilmasi, auto_match'te matched_id'nin TAMAMEN
eksik olmasi) BURADA duzeltilmez - onlar gercek prompt-uyum sorunu, sessizce
yutulmamali (bkz. modul docstring'i "hatalar sessizce yutulmaz").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

Verdict = Literal["auto_match", "review", "ambiguous", "no_match"]

_NULL_STRINGS = {"null", "none", "n/a", ""}


class _DecisionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    matched_id: str | None = None

    @field_validator("matched_id", mode="before")
    @classmethod
    def _normalize_matched_id(cls, v: object) -> object:
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str) and v.strip().lower() in _NULL_STRINGS:
            return None
        return v

    @model_validator(mode="after")
    def _matched_id_consistency(self) -> "_DecisionBase":
        if self.verdict == "no_match" and self.matched_id is not None:
            raise ValueError(
                "'no_match' dedi (eşleşme yok) ama yine de bir id (matched_id) verdi - çelişkili"
            )
        if self.verdict != "no_match" and self.matched_id is None:
            raise ValueError(
                f"'{self.verdict}' dedi (bir eşleşme var) ama hangi kayda eşleştiğini "
                "(matched_id) belirtmedi - çelişkili"
            )
        return self


class ParentDecision(_DecisionBase):
    pass


class SubunitDecision(_DecisionBase):
    pass


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `query` alani KALDIRILDI (2026-07-27, Asama 1 hiz paketi): modele koca
    # sorguyu aynen geri yazdirmak uretimi 2-3 katina cikariyordu ve deger hicbir
    # yerde KULLANILMIYORDU (cagiran taraf sorguyu zaten biliyor).
    parent: ParentDecision
    # Mini ara-adim (2026-07-24, Ege/Geriatri bulgusu): subunit kararindan ONCE
    # modelin sorgudaki EN SPESIFIK birim ifadesini aynen yazmasi istenir
    # (~5-10 token) - tam `reasoning` alaninin geri gelisi DEGIL (o ~200 token
    # ve hiz icin kaldirildi), sadece dikkat cipasi: cok-seviyeli sorgularda
    # ust-seviye tam_eşleşme'li adaya kayma egilimini kirmak icin. Sorguda birim
    # ifadesi yoksa null.
    unit_phrase: str | None = None
    # None = sorguda birim ifadesi hic YOK (bkz. modul docstring'i) - "bulunamadi"
    # ile karistirilmasin, o durum SubunitDecision(verdict="no_match").
    subunit: SubunitDecision | None = None
