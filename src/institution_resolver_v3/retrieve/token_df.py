"""Ayirt edici token kapsamasi - havuz kalitesi kapisi.

NEDEN (olculdu 2026-08-14, 125 sorgu, dort ayri mudahale):
prompt/sema/kirpma ayarlarinin hepsi ayni imzayi verdi - bir kisiti gevsetmek
dogru cevabi bazen kurtariyor ama "bilmiyorum"u daha sik "eminim ki yanlis"a
ceviriyor. Sebep secim degil SECENEK KUMESI: incelenen vakalarin ~yarisinda
dogru cevap havuzda HIC YOK. Model o durumda ne yaparsa yapsin yanilir.

TSR ESIGI ISE YARAMAZ - denenmeden elenmesinin sebebi olculmus vakalar:
    "Malatya Büyükşehir Belediyesi" -> Ordu Büyükşehir Belediyesi   tsr YUKSEK
    "University of South Australia" -> Flinders University          tsr YUKSEK
    "DEVLET MALZEME OFİSİ GENEL MÜD" -> DSI Genel Mudurlugu          tsr YUKSEK
Ucunde de JENERIK kisim ("büyükşehir belediyesi", "university of", "genel
müdürlüğü") skoru sisiriyor; eksik olan NADIR token ("malatya", "australia",
"malzeme"). Yani olcut benzerlik degil, AYIRT EDICI TOKEN KAPSAMASI olmali.

YONTEM: katalogdan token -> dokuman frekansi (df) haritasi cikarilir. Sorgunun
DUSUK df'li tokenleri "ayirt edici" sayilir. Hicbir aday bu tokenlerden HIC
BIRINI tasimiyorsa havuz o sorgu icin coptur - hakeme sorulmadan `no_match`.

Bu, `retrieve/` icinde SAF bir sinyaldir; karari tuketici verir (gate/decide/
tezgah). Esik parametredir, sabit degil - gold olmadan kalibre edilmez.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from institution_resolver_v3.normalize.query_pipeline import normalize

# Bir token'in "kimlik tasiyabilir" sayilmasi icin ust df siniri.
DEFAULT_MAX_DF = 500
# Bu uzunluktan kisa token dikkate alinmaz ("T.C." -> 't','c' gibi parcalar).
DEFAULT_MIN_LEN = 3

# SORGU-KORPUSU df'si DENENDI VE ATILDI (2026-08-14): envanterden ikinci bir df
# haritasi cikarip "sorguda jenerik" tokenleri elemeyi denedik; katkisi 19 yerine
# 20 indirgeme, yani tek vaka. Ikinci bir veri bagimliligina (ve Kaggle'da
# bulunmayan bir dosyaya) degmedi. Katalog df'si tek basina yeterli.

_DEFAULT_PATH = Path("data/processed/token_df.json")
_DEFAULT_SOURCE = Path("data/processed/parent_canonical.jsonl")


def _tokens(text: str) -> list[str]:
    """Sinyalin geri kalaniyla AYNI normalizasyon (aksansiz, noktalamasiz)."""
    return normalize(text).base_no_accent.split()


def build_token_df(records: Iterable[dict]) -> dict[str, int]:
    """Kanonik kayitlardan token -> DOKUMAN frekansi.

    Dokuman frekansi (kac KAYITTA gecti), toplam gecis sayisi DEGIL - bir
    kaydin adinda iki kez gecen token o kaydi bir kez sayar. Ad + alias'larin
    tamami tek bir "belge" gibi ele alinir: sorgu hangi yazimla gelirse gelsin
    ayni kaydi isaret ediyor.
    """
    df: Counter[str] = Counter()
    for r in records:
        parcalar = [r.get("name") or ""]
        parcalar += [a.get("value", "") for a in (r.get("aliases") or [])]
        gorulen = {t for p in parcalar for t in _tokens(p)}
        df.update(gorulen)
    return dict(df)


def write_token_df(jsonl_paths: list[str | Path], out_path: str | Path) -> dict[str, int]:
    """JSONL kanonik dosyalarindan df haritasi uretir ve yazar."""
    kayitlar = []
    for p in jsonl_paths:
        with open(p, encoding="utf-8") as f:
            kayitlar.extend(json.loads(line) for line in f if line.strip())
    df = build_token_df(kayitlar)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(df, ensure_ascii=False), encoding="utf-8")
    return df


@lru_cache(maxsize=2)
def load_token_df(path: str | Path | None = None) -> dict[str, int]:
    """df haritasini yukler (cache'li); yoksa katalogdan URETIR (~3 sn).

    Otomatik uretim bilincli: harita katalogun deterministik bir turevi, ayri
    bir dagitim adimi olmasi gereksiz. Kaynak JSONL de yoksa BOS sozluk doner -
    kapi o zaman hicbir zaman atesleme yapmaz (sessiz devre disi, hata degil).
    """
    p = Path(path or _DEFAULT_PATH)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    if _DEFAULT_SOURCE.exists():
        return write_token_df([_DEFAULT_SOURCE], p)
    return {}


def distinctive_tokens(
    query: str, df: dict[str, int], *, max_df: int = DEFAULT_MAX_DF
) -> list[str]:
    """Sorgunun ayirt edici (dusuk df'li) tokenleri.

    Katalogda HIC gecmeyen token (df=0) de ayirt edicidir - yabanci/yeni bir
    kurum adinin en guclu isareti odur.
    """
    return [t for t in dict.fromkeys(_tokens(query)) if df.get(t, 0) <= max_df]


def candidate_texts(c) -> list[str]:
    """Adayin kapsama icin taranan metinleri: ad + alias'lar."""
    return [c.name or ""] + list(c.raw.get("aliases") or [])


# Oksuz sayilmak icin bir sorgu token'inin havuzdaki HICBIR token'e bu orandan
# fazla benzememesi gerekir. Yazim/diyakritik varyanti korumasi - 85 fazla
# katiydi, OLCULDU: "brasov" vs "brașov" = 83 ve "alaattin" vs "alaaddin" = 75;
# ikisi de dogru cevabi olan sorgulardi ve 85 esikte haksiz yere bloklaniyordu.
DEFAULT_FUZZY_FLOOR = 75.0


def orphan_tokens(
    query: str,
    candidates: list,
    df: dict[str, int],
    *,
    max_df: int = DEFAULT_MAX_DF,
    min_len: int = DEFAULT_MIN_LEN,
    fuzzy_floor: float = DEFAULT_FUZZY_FLOOR,
) -> list[str]:
    """Sorgunun havuzda KARSILIGI OLMAYAN nadir tokenleri.

    Bir token oksuzdur ancak ve ancak:
      1. katalogda nadirse (df <= max_df)  -> kimlik tasiyan bir ad olabilir,
         jenerik tur kelimesi degil;
      2. havuzdaki hicbir adayin ad/alias'inda GECMIYORSA;
      3. havuzdaki hicbir token'e fuzzy olarak yakin DEGILSE (yazim hatasi).

    Oksuz token varsa havuz sorgunun KIMLIK tasiyan parcasini hic icermiyor
    demektir. Olculen vakalar (2026-08-14):
        "Malatya Büyükşehir Belediyesi" -> havuzda 'buyuksehir'+'belediyesi' VAR,
            'malatya' YOK  -> oksuz  -> havuz cop (secilen: Ordu B.B.)
        "University of South Australia" -> 'university','of','south' VAR,
            'australia' YOK -> oksuz (secilen: Flinders University)
        "DEVLET MALZEME OFİSİ GENEL MÜD." -> 'genel','mudurlugu' VAR,
            'malzeme' YOK   -> oksuz (secilen: DSI Genel Mudurlugu)
    Uc vakada da tsr YUKSEKTI - jenerik kisim skoru sisiriyordu; oksuz-token
    olcutu tam da o yanilsamayi kaldiriyor.
    """
    from rapidfuzz import fuzz

    aday_tokenlari: set[str] = set()
    for c in candidates:
        for metin in candidate_texts(c):
            aday_tokenlari.update(_tokens(metin))

    out: list[str] = []
    for t in dict.fromkeys(_tokens(query)):
        if len(t) < min_len:
            continue  # "T.C." -> 't','c' gibi parcalar
        if df.get(t, 0) > max_df:
            continue  # jenerik/yaygin - kimlik tasimaz
        if t in aday_tokenlari:
            continue
        if any(fuzz.ratio(t, a) >= fuzzy_floor for a in aday_tokenlari):
            continue  # yazim hatasi varyanti
        out.append(t)
    return out


# Kapinin bakacagi havuz - iki mod OLCULECEK (2026-08-14):
#   "parent"          : yalniz parent adaylari. Yerelde olculdu: 68 auto_match'in
#                       19'u indirgenir, ~10'u gercekten yanlisti.
#   "parent_filtered" : + parent filtresinden GECMIS subunit'ler. Yanlis
#                       indirgemelerin hepsi tek imzadaydi (oksuz token birim/
#                       kampus kelimesi: 'ilahiyat', 'rheumatology', 'carbondale');
#                       bu mod onlari susturmayi hedefler.
# NOT: TUM subunit havuzunu katmak DENENDI VE ATILDI - 125 bin kayitlik filtresiz
# havuzda hemen her Turkce yer adi geciyor, sinyal seyreliyor (kapi 60->33 dustu
# ama kesinlik %30->%27, yani dogru atesleme de kayboldu).
GATE_MODES = ("parent", "parent_filtered")


def gate_pool(resolve_result, mode: str) -> list:
    """Kapinin kapsama icin tarayacagi aday listesi."""
    if mode == "parent":
        return list(resolve_result.parents)
    if mode == "parent_filtered":
        return list(resolve_result.parents) + [
            s for s in resolve_result.subunits if s.passed_parent_filter
        ]
    raise ValueError(f"bilinmeyen kapi modu {mode!r} - {GATE_MODES}")
