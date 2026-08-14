"""Hakem prompt/sema varyantlari - A/B olcumu icin (bkz. scripts/judge_ab.py).

NEDEN BURADA, `scripts/` ALTINDA DEGIL (2026-08-14, kullanici karari - Secenek A):
deney kodu uretim prompt'unun KOPYASI uzerinde calisirsa zamanla ondan kayar ve
bir noktadan sonra olctugumuz sey gercek sistem degil, kopyasi olur. Onceki
oturumun deney kodu tam da bu yuzden silindiginde 700 cagrilik olcum
tekrarlanamaz hale geldi (bkz. docs/RAPOR_2026-08-14_llm_katmani_deneyleri.md).
Varyantlar bu yuzden uretim prompt'unun KENDISINI parametrize eder.

GUVENLIK: varyant verilmediginde (`None`) ya da `V1` verildiginde uretilen metin
bugunku prompt ile BAYT-DENK olmali. `tests/fixtures/prompt_v1_golden.txt`
duzenlemeden ONCE dondurulan altin kopyadir ve `test_judge_variants.py` her
kosuda ona karsi karsilastirir - tek karakter kaysa test kirmizi doner.

Bayrak ekleme kurali: her bayrak BAGIMSIZ ve UYGULANMIS olmali. Uygulanmamis
bayrak (ileride lazim olur diye) BURAYA EKLENMEZ - okunmayan olu anahtar
birakmama kurali (v2 O6) prompt varyantlari icin de gecerli.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVariant:
    """Tek bir prompt varyanti. `frozen`: koşu boyunca degismesin (aynı nesne
    tum sorgularda paylasilir; yerinde degistirilirse olcum sessizce bozulurdu).

    olu_kurallar: Semanin (Ollama kisitli uretim grameri) ZATEN fiziksel olarak
        zorladigi kurallar prompt'ta dursun mu. `True` = bugunku davranis.
        `False` = su uc blok cikarilir:
          1. "İki liste AYRIDIR ... listeler arası id GEÇERSİZDİR"
             -> `matched_id.enum` zaten yalnız o listenin adaylarini iceriyor
          2. "matched_id ... 'id|ad' biçiminde ... UYDURMA ... null olmalı"
             -> ayni enum + `no_match` dalindaki `const`/`null`
          3. ÇIKTI paragrafi + JSON sema ornegi
             -> gramerin kendisi; metinle tekrar anlatmak
        `verdict` TANIMLARI ("review" ne demek) BILEREK KALIR - onlar semantik
        icerik, sema onlari zorlamiyor; yalniz deger LISTESI enum'da tekrarli.
    """

    name: str = "v1"
    olu_kurallar: bool = True


# Taban: bugunku uretim prompt'u. Butun karsilastirmalar buna gore.
V1 = PromptVariant(name="v1", olu_kurallar=True)

# Olu kurallar cikarilmis surum (prompt-only; sema DEGISMEZ).
# Yanlislanabilir tahmin: rapor +333 token eklemenin modeli daha "kararli"
# yaptigini olctu (auto_match %69->%73, review %3->%1). Iliski gercekse token
# CIKARMAK ters yonde, yani daha temkinli calismali - prompt'un kendi olcutune
# gore dogru yon ("alakasiz bir kayda auto_match vermek cok daha pahali").
V3 = PromptVariant(name="v3", olu_kurallar=False)

REGISTRY: dict[str, PromptVariant] = {v.name: v for v in (V1, V3)}


def get_variant(name: str) -> PromptVariant:
    """Ada gore varyant dondurur; bilinmeyen ad SESSIZ GECILMEZ."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"bilinmeyen varyant {name!r} - taninanlar: {sorted(REGISTRY)}"
        ) from None
