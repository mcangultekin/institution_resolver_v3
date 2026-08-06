"""Turkce-bilincli, merkezi normalizasyon katmani (tasarim.md Bolum 2).

NEDEN bu katman var?
--------------------
Tum eslestirme sisteminin temeli, "iki farkli yazilmis ayni isim, normalize
edildiginde ayni stringe donusmeli" varsayimi. Once burada iki somut hata
duzeltiliyor:

1. Python'un `str.lower()` metodu Turkce "İ"/"I" harflerini yanlis cevirir:
   "İ" (U+0130, noktali buyuk I) -> "i̇" (YANLIS: "i" + gorunmez "combining
   dot above", 2 unicode code point) ve "I" (ASCII buyuk I) -> "i" (YANLIS:
   Turkce'de "ı" -noktasiz kucuk i- olmali). Bu, "TIP" ile "tıp" gibi ayni
   kelimenin eslesmemesine yol acan sessiz bir hata - exception firlatmaz,
   sadece yanlis sonuc uretir. `turkish_lower` kendi acik I/İ cevrim
   tablosuyla bunu duzeltir.
2. Ama Turkce kurali HER metne korukorune uygulanamaz: kendi veri
   taramamizda (bkz. EXPERIMENTS.md) locale="tr" etiketli 39.175 kaydin
   acikca Ingilizce oldugu (ör. "Technical University of Crete") goruldu -
   yani kaynak `locale` alanina guvenilemez. `locale_aware_lower` bunun
   yerine ICERIK kanitina (metinde Turkce'ye ozgu bir karakter var mi) bakar;
   bu v1 demodaki (`reference/v1_demo/normalize.py`) tasarim kararinin
   aynen devralinmasidir.

Bu modul ayrica gorunmez/whitespace temizligi (NBSP/ZWSP/BOM - kendi
taramada sirasiyla 65/302/14 kayitta bulundu, bkz. EXPERIMENTS.md) ve
noktalama temizligini de merkezilestirir. Ingest (`ingest/quality._simple_normalize`),
rerank (`rerank/signals.py`, `normalize/qualifiers.py`) ve tum sorgu/embed
entegrasyon noktalari (bkz. `resolver.py`, `embedding/text_builder.py`,
`elastic/indexer.py`) buradaki tek fonksiyon setini kullanir - kod tekrari
onlenir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from institution_resolver_v3.normalize.abbreviations import expand_known_abbreviations

# --------------------------------------------------------------------------
# 1) Turkce buyuk->kucuk harf cevrim tablosu
# --------------------------------------------------------------------------
_TR_CASEFOLD_MAP = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})


def turkish_lower(text: str) -> str:
    """Turkce kurallarina gore buyuk harften kucuk harfe cevirir.

    UYARI: Bu fonksiyon SADECE Turkce metin icin dogrudur - Ingilizce
    metinde "I" harfi "ı" degil "i" olmali. Metnin dili bilinmiyorsa
    `locale_aware_lower` kullan.
    """
    return text.translate(_TR_CASEFOLD_MAP).lower()


# Turkce'ye ozgu harfler (buyuk+kucuk) - bir metinde bunlardan biri varsa,
# metnin (en azindan kismen) Turkce yazildigindan eminiz.
_TURKISH_SPECIFIC_CHARS = set("çÇğĞıİöÖşŞüÜâÂîÎûÛ")


def _looks_turkish(text: str) -> bool:
    return any(ch in _TURKISH_SPECIFIC_CHARS for ch in text)


def locale_aware_lower(text: str, locale: str | None = None) -> str:
    """Metni BILINEN degil ICERIK kanitina gore kucuk harfe cevirir.

    Karar sirasi locale etiketi degil icerik kanitidir:
    1. Metinde Turkce'ye ozgu bir karakter varsa - KESIN kanit, locale ne
       derse desin `turkish_lower` uygulanir.
    2. Metin tamamen ASCII harflerden olusuyorsa, Turkce mi Ingilizce mi
       ayirt edilemez - locale etiketi de guvenilmez oldugundan (bkz. modul
       docstring'i) duz `.lower()` kullanilir.

    `locale` parametresi su an ikinci adimda kullanilmiyor (bilerek - kaynak
    veride locale="tr" etiketi guvenilmez cikti); yine de gelecekte daha
    guvenilir bir locale kaynagi eklenirse karar agacina eklenebilsin diye
    imzada tutuluyor.
    """
    if _looks_turkish(text):
        return turkish_lower(text)
    return text.lower()


# --------------------------------------------------------------------------
# 2) Aksan/diyakritik temizleme
# --------------------------------------------------------------------------
_TR_ACCENT_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "â": "a", "î": "i", "û": "u",
})


def strip_turkish_accents(lowered_text: str) -> str:
    """Kucuk harfe cevrilmis Turkce metindeki aksanli karakterleri ASCII'ye cevirir."""
    return lowered_text.translate(_TR_ACCENT_MAP)


# --------------------------------------------------------------------------
# 3) Gorunmez karakter / whitespace temizligi
# --------------------------------------------------------------------------
# Kendi veri taramamizda (bkz. EXPERIMENTS.md) bulunan gorunmez karakterler:
# NBSP (U+00A0, 65 kayit), ZWSP (U+200B, 302 kayit), BOM (U+FEFF, 14 kayit).
# Bunlar gorsel olarak fark edilmez ama tokenizer'i/BM25 eslesmesini
# sessizce bozar - normal boslukla degistirilir (BOM/ZWSP/NBSP hepsi "goze
# gorunmeyen ayrac" oldugundan sonucta fark yaratmaz, hepsi normal boslukla
# degistirilip sonra tekile indirgenir).
_INVISIBLE_CHARS = [
    " ",  # NBSP
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # BOM / zero-width no-break space
    " ", " ", " ", " ", " ",
    " ", " ", " ", " ", " ", " ",  # en/em/thin space vb.
    "　",  # ideographic space
]
_INVISIBLE_CHARS_PATTERN = re.compile("[" + "".join(_INVISIBLE_CHARS) + "]")
_MULTI_SPACE_PATTERN = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Gorunmez/genisletilmis boslugu normal booluga cevirir, coklu boslugu tekile indirger."""
    text = _INVISIBLE_CHARS_PATTERN.sub(" ", text)
    return _MULTI_SPACE_PATTERN.sub(" ", text).strip()


# --------------------------------------------------------------------------
# 4) Noktalama temizligi
# --------------------------------------------------------------------------
# Harf VE rakam karakterlerini koruyoruz (bazi birim adlarinda "II", "2"
# gibi rakamlar anlamli olabilir). Kelime-ici tire ("Fen-Edebiyat") ile
# ayirici tire ("Ankara - Turkiye") AYNI sekilde islenir (ikisi de boslukla
# degistirilir) - kendi veri taramamizda ikisinin de esit oranda gorulmesi
# (35.924 vs 5.648 kayit, bkz. EXPERIMENTS.md) ve bu katmanin cikisinin
# yalnizca fuzzy/token-tabanli eslestirme icin kullanilmasi nedeniyle
# (goruntuleme icin degil) bu ayrimin pratik bir faydasi yok: "fen-edebiyat"
# iki token'a bolunmesi, "fen edebiyat fakultesi" sorgusuyla token_set_ratio
# uzerinden zaten dogru eslesiyor - ayri bir kural eklemek gereksiz karmasiklik
# olurdu (bilincli sinirlama, bkz. EXPERIMENTS.md).
_NON_ALNUM_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)


def clean_punctuation(text: str) -> str:
    return _NON_ALNUM_PATTERN.sub(" ", text)


# --------------------------------------------------------------------------
# 5) Sorgu/embed metni icin yapi-koruyan genisletme
# --------------------------------------------------------------------------
# (5b) Parent-sorgusundan alt-birim-ozgu kelimeleri sabit bir listeyle dusurme
# denemesi buradaydi (K4, 2B.2) - `retrieve.decompose.decompose()` bunun
# YERINE gecti: sabit kelime listesi yerine ES'in kendisine sorup kurum
# sinirini ampirik tespit ediyor (bkz. decompose.py docstring'i - Ingilizce
# "University of X" ters-oruntusunde ve Turkce bilesik kurum adlarinda bu
# sabit-liste yaklasimi yetersiz kaliyordu).


def expand_query_text(text: str, locale: str | None = None) -> str:
    """Metnin GORUNUR YAPISINI (buyuk/kucuk harf, aksan) BOZMADAN sadece
    NFKC + gorunmez-karakter temizligi + kisaltma genisletmesi uygular.

    Bu, ES BM25/fuzzy sorgusuna VE embedding'e giden metin icin kullanilir:
    ne dokuman metnini (`display_name`/`aliases.name`) degistiriyoruz (ES
    kendi `turkish_analyzer`/`ascii_analyzer`'i zaten index+sorgu zamaninda
    simetrik calisiyor, bkz. `elastic/mappings.py`) ne de embedding modelinin
    (case/aksan-duyarli coklu-dilli e5) girdisini bozuyoruz - sadece
    kisaltma-genisletmesi (ör. "üni" -> "üniversitesi") ekliyoruz ki
    kullanicinin kisaltilmis sorgusu, veride zaten acik yazilmis dokuman
    metniyle lexical/semantik olarak orussun.
    """
    text = unicodedata.normalize("NFKC", text)
    text = normalize_whitespace(text)
    text = expand_known_abbreviations(text)
    return normalize_whitespace(text)


# --------------------------------------------------------------------------
# 6) Tam normalizasyon: anahtar (keyword) alan uretimi icin
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class NormalizedName:
    """Bir kurum/birim isminin ya da sorgunun tam normalizasyon sonucu.

    `frozen=True`: `normalize()` cache'lendigi icin ayni ornek COK sayida
    cagriya paylasilir - yerinde degistirilebilseydi bir tuketicinin mutasyonu
    cache'i zehirlerdi. Ayni tuzak `embedding/query_encoder.py`'de vektorun
    read-only isaretlenmesiyle kapatilmisti; buradaki karsiligi budur.
    Kod tabaninda hicbir yerde bu nesneye atama YAPILMIYOR (dogrulandi).

    Alanlar:
        raw:            orijinal, dokunulmamis girdi.
        base:           kisaltmalari genisletilmis, locale-bilincli kucuk
                        harf, noktalama/gorunmez-karakter temizlenmis,
                        AKSAN KORUNMUŞ metin.
        base_no_accent: base ile ayni ama aksanlar da temizlenmis (ör.
                        kullanici "universite" diye Turkce karaktersiz
                        yazdiginda bu alanla eslesebilsin diye).
    """

    raw: str
    base: str
    base_no_accent: str

    @property
    def tokens(self) -> list[str]:
        return self.base.split(" ") if self.base else []


@lru_cache(maxsize=100_000)
def normalize(
    raw_text: str,
    *,
    locale: str | None = None,
    expand_abbreviations: bool = True,
) -> NormalizedName:
    """Butun normalizasyon adimlarini sirayla uygulayan ana giris noktasi.

    CACHE'LI (2026-08-06): tek bir sorgu icinde ayni katalog string'i defalarca
    normalize ediliyordu - `decompose` her span x her hit x her ad-varyanti,
    `_attach_signals` her aday x her alias icin cagiriyor; span taramasi O(n^2)
    oldugu icin ayni parent'in ayni alias'i onlarca kez yeniden isleniyordu.
    Saf fonksiyon (girdi -> cikti deterministik, yan etki yok) ve donen nesne
    `frozen` oldugu icin paylasim guvenli.

    Adim sirasi kasitli:
    1. Unicode NFKC normalizasyonu (bilesik/ayrik aksan karakterlerini
       tek bir forma indirger - ör. "e"+combining-acute vs tek code point
       "é" ayni stringe donusur).
    2. Gorunmez karakter/whitespace temizligi (bkz. Bolum 3).
    3. Bilinen kisaltmalari genislet (Bolum 5/`abbreviations.py`) - bu adim
       KUCUK HARFE CEVIRMEDEN ONCE yapilmali, cunku kisaltma regex'leri
       nokta karakterine dayaniyor ve noktalama temizligi (adim 5) bu
       noktalari siler.
    4. Locale-bilincli kucuk harfe cevirme (Bolum 1).
    5. Noktalama temizligi (Bolum 4).
    6. Whitespace'i tekrar normalize et (noktalama temizligi yeni bosluklar
       uretebilir).
    7. Aksansiz varyanti ayrica uret (ikincil anahtar).

    Bu fonksiyonun ciktisi (`base`/`base_no_accent`) esas olarak KEYWORD
    duzeyinde tam esitlik gerektiren yerlerde kullanilir (ör. `Alias.normalized`
    alani, akronim tam-eslesme sorgusu, duplicate tespiti - bkz.
    `ingest/quality._simple_normalize`). ES'e giden BM25 metni ya da embed
    metni icin bunun yerine `expand_query_text` kullanilir (Bolum 5) - o
    fonksiyon buyuk/kucuk harf ve aksan bilgisini KORUR.
    """
    text = unicodedata.normalize("NFKC", raw_text)
    text = normalize_whitespace(text)
    if expand_abbreviations:
        text = expand_known_abbreviations(text)
    text = locale_aware_lower(text, locale)
    text = clean_punctuation(text)
    base = normalize_whitespace(text)
    base_no_accent = strip_turkish_accents(base)
    return NormalizedName(raw=raw_text, base=base, base_no_accent=base_no_accent)
