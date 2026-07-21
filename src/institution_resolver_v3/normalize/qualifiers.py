"""Nitelik (qualifier) cikarimi - tasarim.md 2.4 / EXPERIMENTS.md.

Embedding tezli/tezsiz gibi nitelik farklarini guvenilir sekilde ayirt
edemiyor (bkz. EXPERIMENTS.md), bu yuzden nitelik cikarimi ve celiski
kontrolu regex-tabanli, sert bir kural olarak burada merkezilestirilir.
Onceden `rerank/signals.py` icinde ayri/paralel bir regex seti vardi - bu
modul o mantigin YERINE gecer (`rerank/signals.py` artik bu modulu
sarmalar, kendi kopyasini tutmaz).

Cikarim hem SORGU metni hem de aday (`display_name`/`matched_alias`) metni
uzerinde AYNI fonksiyonla calisir - modelleme `institution_resolver_v3.models.Qualifiers`
ile uyumludur (degree/thesis/language/modality/extra).

Kendi veri taramamizda (bkz. EXPERIMENTS.md) v1'in kapsamadigi/dogru
kapsamadigi 3 yeni bulgu:
1. "(İÖ)" - "ikinci ogretim"in kisaltmasi, 2.118 subunit kaydinda HER ZAMAN
   parantez icinde gorulduk (örn. "... (YL) (TEZLİ) (İÖ)"). Modalite
   sozlugune eklendi.
2. "(DR)" - "doktora" kisaltmasi bazen CIPLAK (parantezsiz) "dr" yerine
   SADECE parantez icinde kullaniliyor (örn. "... (DR)"). Bile bile SADECE
   parantez-ici formu ("\\(dr\\)") destekliyoruz - ciplak "\\bdr\\b" regex'i
   kullanmiyoruz, cunku veride "Prof. Dr. Cemil Tascioglu" gibi bir
   DOKTORUN ADINI tasiyan kurum isimleri de var (bkz. EXPERIMENTS.md,
   264 kayit) - ciplak "dr" regex'i bu isimlerdeki unvani yanlislikla
   "doktora" niteligi sanip celiski uretirdi.
3. Dil niteligi sadece ingilizce/turkce degil - kendi taramamizda almanca
   (133), arapca (146), fransizca (100), rusca (36), ispanyolca (4) da
   anlamli sayida bulundu; sozluge eklendi.
4. "(DİSİPLİNLERARASI)" (2.092 kayit), "(TAM BURSLU)"/"(FULL SCHOLARSHIP)"
   ve "(ÜCRETLİ)"/"(PAID)" - bunlar thesis/modality/language/degree
   boyutlarindan hicbirine girmiyor; `Qualifiers.extra` listesine kanonik
   etiketler olarak ekleniyor (model zaten bu amac icin var, yeni alan
   eklemeye gerek yok).
"""

from __future__ import annotations

import re
from typing import Any

from institution_resolver_v3.models import Qualifiers
from institution_resolver_v3.normalize.query_pipeline import strip_turkish_accents, turkish_lower

_THESIS_PATTERNS: list[tuple[str, bool]] = [
    (r"\btezsiz\b", False),
    (r"\bnon[- ]?thesis\b", False),
    (r"\bwithout thesis\b", False),
    (r"\btezli\b", True),
    (r"\bwith thesis\b", True),
]

_MODALITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bikinci\s*ö?g?retim\b", "ikinci_ogretim"),
    (r"\(\s*iö\s*\)", "ikinci_ogretim"),  # kisaltma - SADECE parantez icinde (bkz. modul docstring'i)
    (r"\buzaktan\s*(egitim|ogretim)\b", "uzaktan"),
    (r"\bdistance\s*education\b", "uzaktan"),
    (r"\bnormal\s*ö?g?retim\b", "normal_ogretim"),
    (r"\börgün\b|\borgun\b", "normal_ogretim"),
]

_LANGUAGE_PATTERNS: list[tuple[str, str]] = [
    (r"\bingilizce\b|\benglish\b", "en"),
    (r"\btürkçe\b|\bturkce\b", "tr"),
    (r"\balmanca\b|\bgerman\b", "de"),
    (r"\bfransızca\b|\bfransizca\b|\bfrench\b", "fr"),
    (r"\barapça\b|\barapca\b|\barabic\b", "ar"),
    (r"\brusça\b|\brusca\b|\brussian\b", "ru"),
    (r"\bispanyolca\b|\bspanish\b", "es"),
    (r"\bitalyanca\b|\bitalian\b", "it"),
]

_DEGREE_PATTERNS: list[tuple[str, str]] = [
    (r"\bdoktora\b|\bphd\b|\bph\.d\.?\b", "phd"),
    (r"\(\s*dr\s*\)", "phd"),  # kisaltma - SADECE parantez icinde (bkz. modul docstring'i)
    # K2 duzeltmesi (bkz. REVIEW_RAPORU.md/ACTION_PLAN.md): "\b\(yl\)\b" hicbir
    # zaman eslesmiyordu ('(' bir kelime-sinir karakteri degil). "\(\s*yl\s*\)"
    # digger parantezli kaliplarla ayni bicimde duzeltildi. Ciplak "\byl\b" de
    # AYRICA eklendi: 285K kayitlik veride yanlis-pozitif taramasi yapildi
    # (bkz. EXPERIMENTS.md "(YL) K2 duzeltmesi"), tum korpusta parantez-DISI
    # "yl" gecen TEK BIR benzersiz kayit bulundu ("... Sanat ve Tasarım YL" -
    # gercek "yuksek lisans" kisaltmasi, yanlis-pozitif degil) - risk ihmal
    # edilebilir.
    (r"\byuksek\s*lisans\b|\byüksek\s*lisans\b|\(\s*yl\s*\)|\byl\b|\bmaster\b|\bmsc\b", "yl"),
    (r"\blisans\b|\bbachelor\b|\bbsc\b", "lisans"),
    (r"\bönlisans\b|\bonlisans\b|\bassociate degree\b", "onlisans"),
]

_EXTRA_PATTERNS: list[tuple[str, str]] = [
    (r"\bdisiplinlerarasi\b|\binterdisciplinary\b", "interdisciplinary"),
    (r"\btam\s*burslu\b|\bfull\s*scholarship\b", "full_scholarship"),
    (r"\bücretli\b|\bucretli\b|\bpaid\b", "paid"),
]

# Aksan-duyarsiz eslesme (bkz. EXPERIMENTS.md "turkish_lower duzeltmesi": Yaklasim A/B
# karsilastirmasi): `turkish_lower` BUYUK-HARF Ingilizce metinde ASCII "I"yi Turkce
# kuralla ("ı") cevirir (ör. "WITH THESIS" -> "wıth thesıs"), bu da yukaridaki
# desenlerin ("\bwith thesis\b") eslesmesini kirar. Dil tahmini (Yaklasim A,
# `locale_aware_lower`) bunu COZMEDI: kayitlarin cogu Turkce+Ingilizce alias'lari
# TEK bir metinde birlestiriyor (bkz. `_candidate_names`/`build_alias_text`), bu
# yuzden icerik-kanitli dil tahmini HEMEN HER ZAMAN "Turkce" sonucuna varip
# turkish_lower'i (dolayisiyla ayni hatayi) TUM metne uyguluyor - veri taramasinda
# yalnizca 65 ek kayit kurtardi (bkz. asagida). Buna karsin aksan-duyarsiz
# karsilastirma (Yaklasim B - burada uygulanan) hem BU sorunu hem de AYRI, onceden
# var olan bir bosluğu (ör. `_MODALITY_PATTERNS`'taki "uzaktan egitim/ogretim"
# deseni doğru-aksanli "uzaktan eğitim/öğretim" ile hic eslesmiyordu) COZDU -
# 2420 ek kayitta dogru tespit saglandi (65'e karsi), 40+ rastgele orneklemde
# YANLIS-pozitif bulunmadi (bkz. EXPERIMENTS.md). Yaklasim A'nin somut riski de
# dogrulandi: ASCII-transliterasyonlu Turkce metin ("TIP FAKULTESI") icerik-
# kanitiyla yanlislikla Ingilizce sayilip "tip fakultesi" (yanlis) uretiyordu.
_THESIS_PATTERNS_ASCII = [(strip_turkish_accents(p), v) for p, v in _THESIS_PATTERNS]
_MODALITY_PATTERNS_ASCII = [(strip_turkish_accents(p), v) for p, v in _MODALITY_PATTERNS]
_LANGUAGE_PATTERNS_ASCII = [(strip_turkish_accents(p), v) for p, v in _LANGUAGE_PATTERNS]
_DEGREE_PATTERNS_ASCII = [(strip_turkish_accents(p), v) for p, v in _DEGREE_PATTERNS]
_EXTRA_PATTERNS_ASCII = [(strip_turkish_accents(p), v) for p, v in _EXTRA_PATTERNS]


def extract_qualifiers(text: str) -> dict[str, Any]:
    """Serbest metinden (sorgu ya da aday adi) nitelik ipuclarini regex ile cikarir.

    Hicbir ipucu bulunamayan alan `None` (extra icin bos liste) kalir -
    "belirtilmemis" ile "celisen deger" arasindaki fark celiski
    kontrolunde onemlidir (bkz. `qualifiers_conflict`).

    `turkish_lower` (kucuk harfe cevirme) uygulanir, SONRA aksanlar silinir
    (`strip_turkish_accents`) ve eslesme ASKI-KATLANMIŞ (ascii-folded) desen
    listeleriyle yapilir - NOKTALAMA yine de TEMIZLENMEZ (parantez-bagimli
    kaliplar - "(dr)", "(iö)" - parantezlerin ayakta kalmasina ihtiyac duyar).
    Aksan-duyarsizlik neden gerekli: bkz. yukaridaki `_THESIS_PATTERNS_ASCII`
    yorumu.
    """
    normalized = strip_turkish_accents(turkish_lower(text))
    result: dict[str, Any] = {"thesis": None, "modality": None, "language": None, "degree": None, "extra": []}
    for pattern, value in _THESIS_PATTERNS_ASCII:
        if re.search(pattern, normalized):
            result["thesis"] = value
            break
    for pattern, value in _MODALITY_PATTERNS_ASCII:
        if re.search(pattern, normalized):
            result["modality"] = value
            break
    for pattern, value in _LANGUAGE_PATTERNS_ASCII:
        if re.search(pattern, normalized):
            result["language"] = value
            break
    for pattern, value in _DEGREE_PATTERNS_ASCII:
        if re.search(pattern, normalized):
            result["degree"] = value
            break
    extra: list[str] = []
    for pattern, value in _EXTRA_PATTERNS_ASCII:
        if re.search(pattern, normalized) and value not in extra:
            extra.append(value)
    result["extra"] = extra
    return result


def extract_qualifiers_model(text: str) -> Qualifiers:
    """`extract_qualifiers` sonucunu `models.Qualifiers` pydantic modeline cevirir."""
    return Qualifiers.model_validate(extract_qualifiers(text))


def qualifiers_conflict(query_qualifiers: dict[str, Any], candidate_qualifiers: dict[str, Any]) -> bool:
    """Iki nitelik setinin herhangi bir boyutta CELISIP celismedigini soyler.

    Yalnizca her iki tarafta da deger belirtilmisse ve degerler farkliysa
    celiski sayilir; biri belirtilmemisse (None) celiski yoktur. `extra`
    listesi celiski kontrolune girmez - o bir "ek bilgi" listesi, iki
    tarafin da ayni sette olmasi beklenmez (ör. sorguda "tam burslu"
    gecmemesi, adayin burslu olmadigi anlamina gelmez).
    """
    for key in ("thesis", "modality", "language", "degree"):
        q_value = query_qualifiers.get(key)
        c_value = candidate_qualifiers.get(key)
        if q_value is not None and c_value is not None and q_value != c_value:
            return True
    return False


def qualifier_match_score(query_qualifiers: dict[str, Any], candidate_qualifiers: dict[str, Any]) -> float:
    """Sorgu nitelik belirtmisse ve aday da ayni degeri tasiyorsa 1.0'a yaklasan sinyal.

    Sorgunun hic nitelik belirtmedigi durumda notr 0.5 doner - ne odul ne
    ceza; celiski zaten `qualifiers_conflict` ile ayrica cezalandirilir.
    """
    keys = ("thesis", "modality", "language", "degree")
    specified = [k for k in keys if query_qualifiers.get(k) is not None]
    if not specified:
        return 0.5
    matches = sum(1 for k in specified if candidate_qualifiers.get(k) == query_qualifiers.get(k))
    return matches / len(specified)
