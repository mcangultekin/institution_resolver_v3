"""500 sorgu icin cok-eksenli kategori atama.

Eksenler birbirine DIK (tek etiketli sema capraz sorulari kaybediyordu:
`sadece_kurum_adi`nin 30/40'i Ingilizce, `turkce_varyasyon`un %80'i cok-parcali).

kurum_tipi  : sorgunun UST SEVIYE (parent) kurum tipi
sorgu_formu : sorgunun yapisi (birim var mi, kac parca)
dil         : YAPISAL kelimelerin dili (ozel isimdeki aksan dili BELIRLEMEZ -
              "University of Health Sciences Diskapi Yildirim Beyazit" Ingilizcedir)
bozulma     : robustluk bayraklari (coklu, '|' ile ayrilir)

NOT: kucuk harfe cevirmede `turkish_lower` KULLANILIR - Python'un `.lower()`i
"ENSTİTÜSÜ" -> "enstİ̇tüsü" uretip regex'i sessizce kiriyor (bkz.
normalize/query_pipeline.py modul docstring'i, ayni tuzak).
"""
import re, sys, unicodedata
sys.path.insert(0, "src")
from institution_resolver_v3.normalize.query_pipeline import turkish_lower, strip_turkish_accents

def _n(s):
    return strip_turkish_accents(turkish_lower(unicodedata.normalize("NFKC", s).replace("\n", " ")))

HASTANE = r"(hastane|hospital|tip merkezi|medical cent(er|re)|klinik|clinic|saglik uygulama|arastirma hastanesi|egitim ve arastirma)"
ENSTITU = r"(enstitu|institute|arastirma merkezi|research cent(er|re)|uygulama ve arastirma merkezi|observator|laboratuvar)"
KAMU    = r"(bakanlig|ministry|mudurlug|baskanlig|genel mudurluk|directorate|belediye|valilik|tubitak|il saglik|ilce milli)"
SIRKET  = r"(\ba\.? ?s\.?($|[ ,.])|\bltd\b|\binc\b|\bcorp\b|\bgmbh\b|\bco\.|\bsan\.|\btic\.|holding|r&d|sanayi|ticaret|fabrikalari|\bteknoloji a)"
UNI     = r"(universit|univ\b|uni\b|fakulte|faculty|college|yuksekokul|akademi|academy|school of)"
BIRIM   = r"(bolum|department|\bdept\b|anabilim|bilim dali|\babd\b|program|fakulte|faculty|klinik|divis|laborat|\bmyo\b|meslek yuksekokulu|enstitu|institute|yuksekokul|school of|\bad\b|muhendislig|konservatuvar|\bsbe\b|\bfbe\b|hastanesi|hospital)"
UNVAN   = r"(\bprof\b|\bdoc\b|\bdr\b|ogr\.? ?gor|ars\.? ?gor|\buzm\b|hemsire|ogretmen|muhendis|avukat|emekli|serbest arastirmaci|independent researcher|\bmd\b)"

EN_YAPISAL = r"\b(of|the|and|for|university|faculty|department|hospital|institute|research|school|center|centre|college|division|laboratory|ministry)\b"
TR_YAPISAL = r"(universitesi|universite|fakultesi|bolumu|bolum|hastanesi|enstitusu|anabilim|bilim dali|mudurlugu|baskanligi|bakanligi|yuksekokulu|merkezi|dali\b|\bve\b)"

def dil(s):
    t = _n(s)
    en = len(re.findall(EN_YAPISAL, t))
    tr = len(re.findall(TR_YAPISAL, t))
    if tr > en: return "tr"
    if en > tr: return "en"
    return "tr" if any(c in "çğıöşü" for c in turkish_lower(s)) else "diger"

def kurum_tipi(s):
    """UST SEVIYE kurum tipi. Universite + enstitu -> universite (enstitu birimdir,
    bunu `sorgu_formu=kurum_birim` tasir)."""
    t = _n(s)
    if re.search(SIRKET, t):  return "sirket"
    if re.search(KAMU, t):    return "bakanlik_kamu"
    if re.search(HASTANE, t): return "hastane"
    if re.search(UNI, t):     return "universite"
    if re.search(ENSTITU, t): return "enstitu_merkez"
    if re.search(UNVAN, t):   return "yok"
    return "yok"

def sorgu_formu(s):
    t = _n(s)
    parts = [p for p in re.split(r"[,;]", t) if p.strip()]
    has_birim = bool(re.search(BIRIM, t))
    if len(parts) >= 3: return "karisik_affiliation"
    if len(parts) == 2: return "kurum_birim" if has_birim else "karisik_affiliation"
    return "kurum_birim" if has_birim else "sadece_kurum"

def bozulma(s):
    f, t = [], unicodedata.normalize("NFKC", s)
    if t.rstrip().endswith("..."): f.append("kirpik")
    if "\n" in s: f.append("satir_sonu")
    L = [c for c in t if c.isalpha()]
    if L and sum(1 for c in L if c == turkish_lower(c).upper() or c.isupper()) / len(L) > 0.85:
        f.append("buyuk_harf")
    if re.search(r"\b\w{2,6}\.(\s|$)", t) or re.search(r"\b(IIBF|MYO|ABD|SBF|FEF|ODTU|ITU|YTU|TOMER|GIT|IIBF)\b", _n(s).upper()):
        f.append("kisaltma")
    return "|".join(dict.fromkeys(f)) or "yok"
