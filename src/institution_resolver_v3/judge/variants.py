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

    Iki BAGIMSIZ bayrak - cunku 14 Agustos olcumu ikisinin ZIT yonde calistigini
    gosterdi (125 sorgu, 35 fark, hepsi tek tek incelendi):

    sema_zorunlu_kurallar: Semanin (llama.cpp grameri) ZATEN fiziksel olarak
        zorladigi iki kural blogu prompt'ta dursun mu.
          1. "İki liste AYRIDIR ... listeler arası id GEÇERSİZDİR"
             -> `matched_id.enum` zaten yalnız o listenin adaylarini iceriyor
          2. "matched_id ... 'id|ad' biçiminde ... UYDURMA ... null olmalı"
             -> ayni enum + `no_match` dalindaki `const`/`null`
        OLCULDU: cikarmak modeli parent'ta belirgin daha TEMKINLI yapiyor -
        dogru cevabin havuzda OLMADIGI 16 sorguda yanlis `auto_match` yerine
        `no_match` dedi (Iğdır MYO -> İstanbul Şişli MYO, Bursa EAH -> Ankara
        Gülhane, Trakya Tarımsal Arş. Ens. -> TRAKYA ÜNİVERSİTESİ gibi).

    sema_ornegi: ÇIKTI paragrafi + JSON sema ornegi dursun mu.
        "Olu kural" sanilmisti, DEGILMIS (14 Agustos, kanitli): ornekteki
        `"unit_phrase": ... | null` ve `"subunit": {...} | null` isaretleri
        modelin `null` secenegini goren TEK ipucu - gramer buna izin veriyor
        ama ZORLAMIYOR. Cikarinca 18 vaka bozuldu: 11 ciplak kurum sorgusunda
        `subunit` null yerine `no_match` oldu (model kurumun kendi adini
        birim ifadesi sandi, ikisinde `unit_phrase`e LITERAL 'null' DIZGESI
        yazdi), 5 vakada olmayan birim uydurdu, 2 vakada gecersiz JSON uretti.

    bagli_sema: PROMPT DEGIL **SEMA** degisikligi - tek varyant bayragi o
        katmana dokunuyor. Bugun `parent` ve `subunit` enum'lari BAGIMSIZ; model
        P3 ile S5'i birlikte secebiliyor ama S5 gercekte P7'ye bagli olabiliyor
        ve `_validate_ids` TUM SATIRI reddediyor (uretimde olculdu: %7,7 kayip -
        3000 sorguda 232 satir, envanterde 34.299 satir). Ustelik prompt modele
        "kararlari AYRI ayri ver" diyor; model soyleneni yaptigi icin
        cezalandiriliyor.
        `True` iken ust seviyeye `anyOf`: her parent adayi icin bir dal, o dalda
        subunit enum'u YALNIZ o parent'a bagli adaylari icerir - tutarsiz cift
        FIZIKSEL OLARAK uretilemez. Prompt'taki celiskili cumle de duzeltilir
        (bkz. prompt.py `_BOUND_*`), yoksa modele yalan bir dunya tarif edilir.

        BEDELI BILINIYOR (onceki oturum olctu, 100 sorgu): uyusmazlik hatasi bir
        defekt oldugu kadar bir KAFA KARISIKLIGI DEDEKTORU'ydu - model tutarsiz
        cift sectiginde "ne yaptigimi bilmiyorum" diyordu. Ifade edilemez olunca
        kafasi karisikken TUTARLI AMA YANLIS bir sey secip guvenle soyluyor
        (14 duzelmenin 10'u auto_match'e dondu, yalniz 1'i dogruydu). Bu yuzden
        dedektor SILINMIYOR, `judge._confusion_signal` ile KODA tasindi.

        YAPISAL YAN ETKI: parent'i aday listesinde olmayan bir subunit bagli
        semada HIC SECILEMEZ. Bugun de yanlis secilirdi (ve reddedilirdi), ama
        artik sessizce erisilemez - bilinen ve kabul edilen daralma.

    `verdict` TANIMLARI ("review" ne demek) HER ZAMAN KALIR - onlar semantik
    icerik, sema onlari zorlamiyor.
    """

    name: str = "v1"
    sema_zorunlu_kurallar: bool = True
    sema_ornegi: bool = True
    bagli_sema: bool = False


# Taban: bugunku uretim prompt'u. Butun karsilastirmalar buna gore.
V1 = PromptVariant(name="v1")

# Her ikisi de cikarilmis surum. 14 Agustos'ta olculdu: 35/125 karar degisti,
# 16 kazanc (parent temkini) / 18 kayip (null davranisi) - basabas ama iki etki
# FARKLI bloklardan geliyor ve birbirine karismiyor. Tarihsel referans olarak
# korunur; ciktisi tests/fixtures/prompt_v3_golden.txt ile kilitli.
V3 = PromptVariant(name="v3", sema_zorunlu_kurallar=False, sema_ornegi=False)

# v3'un olcumunden dogan varyant: kazandiran blogu cikar, hasar vereni tut.
# YANLISLANABILIR TAHMIN: v4, v1'e gore parent'ta daha temkinli olmali (v3'un
# 16 kazanci) ama `null`/subunit davranisini BOZMAMALI (v3'un 18 kaybi
# tekrarlanmamali). Tahmin tutmazsa hikaye coker: kazanc blok 1+2'den degil
# salt token azalmasindan geliyor demektir.
V4 = PromptVariant(name="v4", sema_zorunlu_kurallar=False, sema_ornegi=True)

# v4 + BAGLI SEMA. v4 uzerine kuruldu (v1 degil) cunku v4 olculdu ve kazandi
# (27-8, 125 sorgu); boylece v4 <-> v5 farki YALNIZ sema degisikligini izole eder.
# ADLANDIRMA: onceki oturumun raporu bagli semaya "v4" diyor - bizim v4'umuz
# prompt varyanti. Karismasin diye buranin adi "v5-bagli".
V5 = PromptVariant(
    name="v5-bagli", sema_zorunlu_kurallar=False, sema_ornegi=True, bagli_sema=True
)

REGISTRY: dict[str, PromptVariant] = {v.name: v for v in (V1, V3, V4, V5)}


def get_variant(name: str) -> PromptVariant:
    """Ada gore varyant dondurur; bilinmeyen ad SESSIZ GECILMEZ."""
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"bilinmeyen varyant {name!r} - taninanlar: {sorted(REGISTRY)}"
        ) from None
