"""Kurum adlarinda sistematik gecen kisaltmalarin genisletilmesi.

Kaynak: reference/v1_demo/normalize.py (onceki deney turundan kurasyonlu
sozluk). EXPERIMENTS.md'de belgelendigi uzere, v2'nin gercek verisi
(data/raw/institution_parent.csv + institution_subunit.csv, ~285K satir)
uzerinde her kalibin frekansi ayrica olculdu. Iki onemli fark cikti:

1. v2'nin belge tarafi (ozellikle subunit adlari) v1'in kestiginden FARKLI
   bir kesitten geliyor: cogu ad zaten ACIK (genisletilmis) yaziliyor - ornegin
   "BÖLÜMÜ", "FAKÜLTESİ" tam yazili, kisaltilmis degil. Bu yuzden v1'in
   verdigi frekanslar (ör. BÖL. icin 40.364) burada birebir tutmuyor (BÖL.
   icin sadece 5). Bu, sozlugun degersiz oldugu anlamina gelmez - kisaltma
   asıl SORGU tarafinda (kullanicinin serbest metninde) ortaya cikiyor;
   belge tarafi zaten temiz oldugu icin kisaltma kaliplari nadir gorunuyor.
   Belge tarafinda GERCEKTEN yaygin olan tek kisaltma PR./PRG. -> PROGRAMI:
   28.533 subunit kaydinda tam olarak "PR." ile bitiyor (bkz. EXPERIMENTS.md).
2. Kendi tarama sonucunda MUH. (Turkce Ü yerine ASCII U ile yazilmis,
   MÜH.'nin harf-hatali/ASCII varyanti) ek olarak bulundu; MÜH. ile ayni
   anlama geliyor, sozluge eklendi.
3. Dogrulama asamasinda (bkz. EXPERIMENTS.md "Aşama 4") tam eval'de
   `abbreviation` gurultu turunde beklenen kazanc CIKMADIGI goruldu -
   kok neden: `eval/noise.py`nin urettigi kisaltmalar arasinda ASCII
   (aksansiz) formlar da var ("uni", "bol" gibi - Turkce klavyesi olmayan
   kullanicilarin gercekte yazacagi formlar), ama asagidaki regex'ler
   SADECE Turkce aksanli harfi (Ü/Ö/Ş/Ğ/İ) hedefliyordu, ASCII karsiligini
   (U/O/S/G/I) degil - MUH. disinda (o zaten elle eklenmisti). Duzeltme:
   Ü/Ö/Ş/Ğ/İ gecen her kalibin regex'i simdi [ÜU]/[ÖO]/[ŞS]/[ĞG]/[İI]
   karakter sinifiyla HER İKİ formu da kabul ediyor.

DISLANAN riskli kisaltmalar (v1'den devralinan, kendi veride de dogrulanan
belirsizlik): TEK. (TEKNOLOJİSİ/TEKNİK/TEKNOLOJİ arasinda baskin anlam yok;
kendi veride de sadece 3 kayit - hem az hem belirsiz) ve BİL. tek basina
(BİLİMLERİ/BİLGİSAYAR belirsizligi; kendi veride 2 kayit - ayni sekilde
az VE belirsiz). Bilesik formlari (SOS.BİL., FEN BİL., SAĞLIK BİL.) belirsiz
degil, sozlukte kaliyor.

Ingilizce kisaltmalar (2026-07-14, manuel 4-sorgu testi sirasinda bulunan
bosluk - bkz. EXPERIMENTS.md "Ingilizce akademik kisaltma genisletmesi"):
locale="en" etiketli 313.291 alias uzerinde nokta-biten token frekansi
sayildi. Belge tarafinda zaten en az bu kadar sik olan ve kurum-yapisi
anlamina gelen (kisi unvani/sokak/sirket eki DEGIL) kisaltmalar eklendi:
FAC. (74) -> FACULTY, INST. (38) -> INSTITUTE, ENG. (106) -> ENGINEERING,
DEPT. (14) -> DEPARTMENT. UNIV./UNIV/UNI. (67+22) BILEREK eklenmedi: ayni
harfler zaten yukaridaki Turkce ÜNİ/UNV kaliplarinca (ASCII-klavye
desteği icin [ÜU] karakter sinifiyla) tuketiliyor - Ingilizce "univ."
sorgusu bu yuzden hala "ÜNİVERSİTESİ"ye genisliyor (Turkce/Ingilizce
karisimi), bilinen ama bu degisiklik kapsami disi birakilan bir sinirlama
(4 test sorgusunun hicbiri ciplak "uni"/"univ." icermiyor, dolayisiyla bu
sinirlama gozlemlenen tutarsizligi ACIKLAMIYOR - bkz. EXPERIMENTS.md).
DR./PROF./ST./CORP./LTD./INC. gibi yuksek frekansli ama kisi
unvani/sirket-eki olan kaliplar bilerek DISLANDI (kurum-yapisi kisaltmasi
degil, veri taramasinda goruldugu gibi cogunlukla farkli anlam tasiyor).
"""

from __future__ import annotations

import re

# ASCII-klavye kullanicilarin (Turkce harf tuslari olmadan) yazacagi formlari
# da kapsamak icin Turkce aksanli harflerin ASCII karsiligiyla alternatifli
# karakter siniflari (bkz. modul docstring'i, madde 3).
_U = "[ÜU]"  # Ü/U
_O = "[ÖO]"  # Ö/O
_S = "[ŞS]"  # Ş/S
_G = "[ĞG]"  # Ğ/G
_I = "[İI]"  # İ/I (ASCII I)

# Siralama onemli: cok-kelimeli/ozgun kisaltmalari once yerlestiriyoruz ki
# daha kisa/genel bir kaliba erken tuketilmesinler.
_ABBREVIATION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --- Cok-kelimeli kisaltmalar once ---
    (re.compile(rf"\bSOS\.?\s*B{_I}L\.", re.IGNORECASE), "SOSYAL BİLİMLERİ"),
    (re.compile(rf"\bFEN\s+B{_I}L\.", re.IGNORECASE), "FEN BİLİMLERİ"),
    (re.compile(rf"\bSA{_G}LIK\s+B{_I}L\.", re.IGNORECASE), "SAĞLIK BİLİMLERİ"),
    # MYO: noktali ve noktasiz her iki formda da guvenli (cok ozgun kisaltma)
    (re.compile(r"\bM\.?Y\.?O\.?\b", re.IGNORECASE), "MESLEK YÜKSEKOKULU"),
    (re.compile(r"\bMYO\.?\b", re.IGNORECASE), "MESLEK YÜKSEKOKULU"),
    # ABD. SADECE noktali formda: "ABD" noktasiz = "Amerika Birlesik Devletleri"
    (re.compile(r"\bA\.?B\.?D\.", re.IGNORECASE), "ANABİLİM DALI"),
    (re.compile(r"\bABD\.", re.IGNORECASE), "ANABİLİM DALI"),
    # Y.O. hem noktali hem noktasiz (YO yalniz bir sozcuk olmaz, ozgun kisaltma)
    (re.compile(r"\bY\.?O\.?\b", re.IGNORECASE), "YÜKSEKOKULU"),
    (re.compile(r"\bYO\.?\b", re.IGNORECASE), "YÜKSEKOKULU"),
    (re.compile(rf"\bY{_U}K\.?\s*OKL\.?\b", re.IGNORECASE), "YÜKSEKOKULU"),
    # --- Tek-kelimeli kisaltmalar ---
    (re.compile(r"\bPR\.", re.IGNORECASE), "PROGRAMI"),
    (re.compile(r"\bPRG\.", re.IGNORECASE), "PROGRAMI"),
    # ÜNİ/ÜNİV/ÜNV/ÜN: hem noktali hem noktasiz
    (re.compile(rf"\b{_U}N{_I}V?\.?\b", re.IGNORECASE), "ÜNİVERSİTESİ"),
    (re.compile(rf"\b{_U}NV\.?\b", re.IGNORECASE), "ÜNİVERSİTESİ"),
    (re.compile(rf"\b{_U}N\.\b", re.IGNORECASE), "ÜNİVERSİTESİ"),
    # FAK: hem noktali hem noktasiz
    (re.compile(r"\bFAK\.?\b", re.IGNORECASE), "FAKÜLTESİ"),
    # ENS/ENST: hem noktali hem noktasiz
    (re.compile(r"\bENST?\.?\b", re.IGNORECASE), "ENSTİTÜSÜ"),
    # BÖL: hem noktali hem noktasiz
    (re.compile(rf"\bB{_O}L\.?\b", re.IGNORECASE), "BÖLÜMÜ"),
    # MÜH: hem noktali hem noktasiz + ASCII/harf-hatali MUH varyanti (kendi
    # taramamizda bulundu, MÜH ile ayni anlam) - _U karakter sinifi zaten
    # MUH'u da kapsiyor ama MUH ayrica elle birakildi (belgelenmis bulgu).
    (re.compile(rf"\bM{_U}H\.?\b", re.IGNORECASE), "MÜHENDİSLİĞİ"),
    (re.compile(r"\bMRKS?\.?\b", re.IGNORECASE), "MERKEZİ"),
    (re.compile(rf"\bAR{_S}T?\.?\b", re.IGNORECASE), "ARAŞTIRMA"),
    (re.compile(r"\bUYG\.?\b", re.IGNORECASE), "UYGULAMA"),
    (re.compile(rf"\bE{_G}T\.?\b", re.IGNORECASE), "EĞİTİMİ"),
    (re.compile(rf"\bY{_O}N\.?\b", re.IGNORECASE), "YÖNETİMİ"),
    (re.compile(r"\bHAST\.?\b", re.IGNORECASE), "HASTANESİ"),
    # --- Ingilizce akademik kisaltmalar (bkz. modul docstring'i) ---
    (re.compile(r"\bFAC\.?\b", re.IGNORECASE), "FACULTY"),
    (re.compile(r"\bDEPT\.?\b", re.IGNORECASE), "DEPARTMENT"),
    (re.compile(r"\bINST\.?\b", re.IGNORECASE), "INSTITUTE"),
    (re.compile(r"\bENG\.?\b", re.IGNORECASE), "ENGINEERING"),
]


def expand_known_abbreviations(text: str) -> str:
    """Bilinen kisaltmalari genisletir (buyuk/kucuk harf duyarsiz).

    Kucuk harfe cevirme/aksan temizligi/noktalama temizliginden ONCE
    cagirilmali (bkz. `normalize.query_pipeline.normalize`) - regex'ler
    kelime siniri VE nokta karakterine dayaniyor, noktalama temizligi
    noktalari sildikten sonra bu kaliplar artik eslesmez.
    """
    for pattern, expansion in _ABBREVIATION_PATTERNS:
        text = pattern.sub(expansion, text)
    return text
