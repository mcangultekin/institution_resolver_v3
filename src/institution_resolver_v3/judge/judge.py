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

import dataclasses
import json

from pydantic import ValidationError

from institution_resolver_v3.judge.candidates import CandidateView, build_candidate_views
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.judge.prompt import build_prompt
from institution_resolver_v3.judge.schema import JudgeResult, SubunitDecision
from institution_resolver_v3.retrieve.resolve import ResolveResult


_VERDICTS = ["auto_match", "review", "ambiguous", "no_match"]


_NO_MATCH_BRANCH: dict = {
    "type": "object",
    "properties": {"verdict": {"const": "no_match"}, "matched_id": {"type": "null"}},
    "required": ["verdict", "matched_id"],
}


def _decision_schema(choices: list[str]) -> dict:
    """Tek bir karar blogu (parent ya da subunit) icin kisitli JSON semasi.

    `matched_id` SADECE bu bloga ait "etiket|ad" degerlerinden biri ya da null
    olabilir - boylece (1) iki listeyi karistirip birinden id cekme (canli bulgu
    2026-07-24: parent alanina subunit listesindeki 105863 yazildi) ve (2) niyet
    edilen adayla yazilan id'nin ayrismasi (Gazi/Cardiology: model dogru adayi
    gorurken komsu kaydin id'sini yazdi - id soyut bir sembol, kucuk model onu
    isimle BAGLAMIYOR) uretim asamasinda engellenir: deger, adayin ADINI da
    icerdigi icin secim ismin semantigine kilitlenir. `_validate_ids` yine de
    kalir (kusak + pantolon askisi - sema destegi olmayan bir client enjekte
    edilirse tek koruma o).

    `verdict` ve `matched_id` BAGIMSIZ iki soru DEGIL - capraz-alan kisiti
    (J1/J2, 05_judge_ve_decide.md) burada semaya kodlanir: eskiden ikisi ayri
    ayri sorulup {"verdict":"auto_match","matched_id":null} gibi celiskili bir
    cikti model tarafindan URETILEBILIYORDU (pydantic sonradan reddediyordu,
    ama LLM cagrisi zaten harcanmis, retry de yok - sorgu tumden basarisiz
    oluyordu). Simdi tek bir "hangi karar + hangi kayit" secimi sunuluyor:
    ya "eslesme yok" (id otomatik bos) ya da "su id ile su karar" (ikisi
    birlikte kilitli) - ucuncu, tutarsiz bir kombinasyon uretim asamasinda
    imkansiz."""
    if not choices:
        # J2: aday havuzu bossa tek gecerli cikti no_match - baska hicbir
        # sey (auto_match/review/ambiguous) secilemez.
        return _NO_MATCH_BRANCH

    matched_branch = {
        "type": "object",
        "properties": {
            "verdict": {"enum": [v for v in _VERDICTS if v != "no_match"]},
            "matched_id": {"enum": choices},
        },
        "required": ["verdict", "matched_id"],
    }
    return {"anyOf": [_NO_MATCH_BRANCH, matched_branch]}


def _choice(v: CandidateView) -> str:
    """Sema enum degeri: "etiket|ad (diger_ad)" (bkz. _decision_schema docstring'i).

    diger_ad (best_alias, cogunlukla Ingilizce) da eklenir: sorgu Ingilizce,
    katalog adi Turkce oldugunda secim-degeri sorgudaki ifadeyle ayni dilde bir
    parca tasisin diye (2026-07-24 Ege bulgusu: model unit_phrase'e "Division of
    Geriatrics" yazip secimde yine de Turkce-adli yanlis adaya gitti - koprunun
    kendisi enum degerinin ICINDE olmali)."""
    return f"{v.id}|{v.name} ({v.best_alias})" if v.best_alias else f"{v.id}|{v.name}"


def build_format_schema(
    parents: list[CandidateView], subunits: list[CandidateView]
) -> dict:
    """Ollama kisitli-uretim semasi: JudgeResult'in aynasi + aday enum'lari."""
    return {
        "type": "object",
        "properties": {
            "parent": _decision_schema([_choice(c) for c in parents]),
            # subunit'ten ONCE gelir (llama.cpp grammar'i property sirasini
            # korur): model once sorgudaki en spesifik birim ifadesini yazmaya
            # zorlanir, subunit secimini ondan SONRA yapar (dikkat cipasi,
            # bkz. schema.py unit_phrase notu).
            "unit_phrase": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "subunit": {
                "anyOf": [
                    _decision_schema([_choice(c) for c in subunits]),
                    {"type": "null"},
                ]
            },
        },
        "required": ["parent", "unit_phrase", "subunit"],
    }


class JudgeValidationError(RuntimeError):
    """LLM ciktisi sema disi ya da aday havuzunda olmayan bir id iceriyor.

    Ana mesaj (`str(exc)`) SABIT/JENERIK - sorgu basina degisen isim/id
    icermez (2026-07-30, kullanici karari: kisa ve tutarli olsun). Sorguya
    ozel ayrinti `debug` alaninda ayrica tasinir - "info butonu" gibi
    istege bagli gosterim icin (API `detail.debug`, CLI `--debug` benzeri;
    varsayilan gorunumde gizli). Eskiden (2026-07-24, "anlasilir hata
    mesaji" talebi) tek bir uzun cumleye gomuluyordu, artik ikiye ayrildi."""

    def __init__(self, message: str, *, debug: str | None = None) -> None:
        super().__init__(message)
        self.debug = debug


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
    """Katalog-karsi dogrulama: uydurma id (halusinasyon) VE parent/subunit
    tutarsizligi (2026-07-30) ayni sinif hata - ikisi de "hakemin dedigi,
    katalogdaki gercekle celisiyor" demek, sessizce gecilmez."""
    parent_ids = {c.id for c in parents}
    subunit_by_id = {c.id: c for c in subunits}
    if result.parent.matched_id is not None and result.parent.matched_id not in parent_ids:
        raise JudgeValidationError(
            "Hakem geçersiz bir cevap verdi (bilinmeyen kurum kaydı).",
            debug=f"parent.matched_id={result.parent.matched_id!r} aday havuzunda yok (halüsinasyon).",
        )
    if result.subunit is not None and result.subunit.matched_id is not None:
        if result.subunit.matched_id not in subunit_by_id:
            raise JudgeValidationError(
                "Hakem geçersiz bir cevap verdi (bilinmeyen alt-birim kaydı).",
                debug=f"subunit.matched_id={result.subunit.matched_id!r} aday havuzunda yok (halüsinasyon).",
            )
        sub_view = subunit_by_id[result.subunit.matched_id]
        if (
            result.parent.matched_id is not None
            and sub_view.parent_id is not None
            and sub_view.parent_id != result.parent.matched_id
        ):
            raise JudgeValidationError(
                "Hakem tutarsız bir cevap verdi (kurum/birim uyuşmazlığı).",
                debug=(
                    f"subunit={sub_view.name!r} gerçek parent_id={sub_view.parent_id!r}, "
                    f"ama hakemin seçtiği parent.matched_id={result.parent.matched_id!r}."
                ),
            )


def _label_views(
    views: list[CandidateView], prefix: str
) -> tuple[list[CandidateView], dict[str, str]]:
    """Gercek katalog id'lerini kisa sentetik etiketlerle (P1.., S1..) degistirir.

    Neden (2026-07-24, Gazi/Cardiology canli bulgusu): kucuk model (E2B) uzun ve
    birbirine benzeyen rakamsal id'leri KARISTIRIYOR - dogru adayi ("152078",
    listenin 1.si, alias'i sorguyla birebir ortusuyor) niyetleyip komsu kaydin
    id'sini ("152062") yazdi; onceki "105863" parent hatasi da ayni kalip. Kisa
    etiket + sema-enum birlikte bu hata sinifini uretim asamasinda kapatir;
    cevap `_unlabel` ile gercek id'ye cevrilir, disari etiket SIZMAZ."""
    labeled = [dataclasses.replace(v, id=f"{prefix}{i + 1}") for i, v in enumerate(views)]
    return labeled, {f"{prefix}{i + 1}": v.id for i, v in enumerate(views)}


def judge(resolve_result: ResolveResult, client: LlmClient) -> JudgeResult:
    """resolve() ciktisini hakeme sorar, dogrulanmis `JudgeResult` doner."""
    parents, subunits = build_candidate_views(resolve_result)
    parents_lbl, p_map = _label_views(parents, "P")
    subunits_lbl, s_map = _label_views(subunits, "S")
    prompt = build_prompt(
        resolve_result.query, resolve_result.decomposed, parents_lbl, subunits_lbl
    )
    raw = client.generate(prompt, format_schema=build_format_schema(parents_lbl, subunits_lbl))

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JudgeValidationError(
            "Hakem geçerli bir yanıt döndürmedi (biçim hatası).",
            debug=f"JSON parse hatası: {exc}. Ham çıktının başı: {raw[:200]!r}",
        ) from exc

    try:
        result = JudgeResult.model_validate(payload)
    except ValidationError as exc:
        raise JudgeValidationError(
            "Hakemin cevabı şemaya uymuyor (çelişkili/eksik alan).",
            debug=_format_validation_error(exc),
        ) from exc

    # "etiket|ad" -> gercek id cevirisi (bkz. _label_views/_choice). Haritada
    # olmayan bir deger oldugu gibi birakilir - _validate_ids onu yakalar
    # (sahte/test client'lari gercek id de dondurebilir, o yol da calismali).
    def _to_real(value: str | None, mapping: dict[str, str]) -> str | None:
        if value is None:
            return None
        label = value.split("|", 1)[0]
        return mapping.get(label, value)

    result.parent.matched_id = _to_real(result.parent.matched_id, p_map)
    if result.subunit is not None:
        result.subunit.matched_id = _to_real(result.subunit.matched_id, s_map)

    _validate_ids(result, parents, subunits)

    # 2026-07-30 (kullanici karari, gate'teki ayni ilke): parent no_match ise
    # (matched_id=None), subunit bir KIMLIK oneremez - subunit adlari parent'lar
    # arasinda kitlesel tekrarlanabiliyor (ör. "bilgisayar muhendisligi bolumu"
    # x190), parent bilinmeden secilen id N aday arasindan bir tahmindir. Bu bir
    # celiski DEGIL (bkz. _validate_ids'teki parent/subunit uyusmazligi - o
    # reddedilir), o yuzden hata firlatilmaz, asagi indirgenir. verdict de
    # no_match'e cekilir - schema.py _matched_id_consistency, verdict!=no_match
    # icin matched_id'yi zorunlu kilar, ikisi birlikte degismeli.
    if (
        result.subunit is not None
        and result.subunit.matched_id is not None
        and result.parent.matched_id is None
    ):
        result.subunit = SubunitDecision(verdict="no_match", matched_id=None)

    return result
