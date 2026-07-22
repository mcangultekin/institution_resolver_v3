"""Sorgu ayristirma: kurum kismi / birim kismi (SIRADAKI ISLER 1, docs/DURUM.md).

NEDEN kural-tabanli (marker/regex) DEGIL?
------------------------------------------
Ilk tasarim "sorguyu 'universitesi/enstitusu/hastanesi/...' gibi bir isaretci
kelimede bol" seklindeydi. Gercek veriyle (106.183 parent kaydi) test edilince
IKI ayri, kanitlanmis kirilma noktasi bulundu:

1. Ingilizce "X of Y" ters-oruntusu: "University of Oxford" gibi adlarda
   isaretci ("university") kurumun adini BASLATIYOR, BITIRMIYOR. Ilk-isaretci
   kuralinda kesersek "university" tek basina kalir, "of Oxford" (kurumun
   kendi adinin parcasi) birim sanilir. Korpusta 106.183 parent'in ~%8'i
   (university/institute/hospital/college/academy of X toplam ~8.566 kayit)
   bu oruntude - gormezden gelinemeyecek boyutta.
2. Turkce bilesik ad: "Eskisehir Osmangazi Universitesi Tip Fakultesi
   Hastanesi" gibi 15 parent kaydi, ZINCIRLEME birden fazla isaretci
   iceren TEK bir kurumun kendi adi (universiteye bagli ama AYRI bir parent
   kaydi olan hastane). Ilk-isaretci kuralinda "...Universitesi" da keserdik,
   bu da compound adi yanlis/eksik yakalardi.

Dil-ozel istisna listeleri (of/für/de/di gibi baglaçlar) eklemek "ilkel ve
hatalara gebe" bulundu (kullanici degerlendirmesi) - her yeni dil/oruntu icin
yeni bir kural eklemek gerekirdi. Bunun yerine KURAL YAZMIYORUZ, VERIYE
SORUYORUZ: kurum adlari zaten indekste GERCEK OLARAK var, o yuzden "kurum
kismi nerede bitiyor" sorusunun cevabini indeksin kendisinden aliyoruz.

YONTEM
------
Sorgunun her olasi kesim noktasini dene (1 token, 2 token, ... tum tokenlar).
Her aday parca icin ES'te (BM25, ucuz - embedding YOK) en yakin parent'lari
bul, `rapidfuzz.fuzz.ratio` (uzunluk-duyarli DUZ oran - `token_set_ratio`
DEGIL, o fazla/eksik kelimeye goz yumdugu icin siniri ayirt edemiyor, bkz.
asagidaki not) ile aday parcanin bulunan parent adina NE KADAR TAM ORTUSTUGUNU
olc. Hangi kesim noktasi bir gercek parent adina neredeyse birebir (~100)
uyuyorsa, kurum siniri orasi - kurum adinin kendisi kadar uzayip kendisinden
fazla uzamiyor. Testlerde (bkz. tests/unit/test_decompose.py) hem Ingilizce
"of" oruntusu hem Turkce bilesik ad hem de "hicbir kurum yok" durumu (duz
skorlarin hicbiri 100'e yaklasmiyor) dogru sekilde ayirt edildi.

`token_set_ratio` DEGIL `ratio` kullanma nedeni: `token_set_ratio` fazla/eksik
kelimeye tolerans gosterir (kesisim tam ise 100 dondurur, adayin FAZLADAN
kelimesi olsa bile) - bu da her kesim noktasinin ayni sekilde 100 almasina
(hicbir ayirt edicilik kalmamasina) yol aciyordu. `ratio` uzunluk farkina
duyarli oldugu icin dogru sinirda net bir PIK olusuyor.

Esiksiz: en yuksek skoru veren kesim noktasi secilir (esitlikte DAHA UZUN
parca tercih edilir - bilesik ad durumunu doguru cozer). Hicbir zorlama esik
YOK (esik tahmini icin etiketli set gerekiyor, bkz. docs/DURUM.md calisma
tarzi) - dusuk-guven bir bolme bile zarar vermez, cunku cagiran taraf
(retrieve/resolve.py) HER ZAMAN filtresiz aramayi da tutup birlestirir
(recall-guvenli cascade).

Not: decompose artik SAF DEGIL, ES'e bagimli (arama fonksiyonu enjekte
edilir - testlerde sahte/mock search_fn kullanilir, gercek ES gerekmez).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rapidfuzz import fuzz

from institution_resolver_v3.normalize.query_pipeline import expand_query_text, normalize

SearchFn = Callable[[str, str], list[dict[str, Any]]]


@dataclass
class DecomposedQuery:
    """Sorgu ayristirma sonucu.

    institution_part: kurum adi oldugu tahmin edilen kisim (parent aramasinda kullanilir).
    unit_part: geri kalan kisim (bos olabilir - kurum disinda birim bilgisi yoksa
               ya da tum sorgu zaten kurumun kendi (bilesik) adiysa).
    boundary_score: secilen sinirin rapidfuzz.fuzz.ratio guven skoru (0-100).
                    Dusuk skor = sorguda net bir kurum adi bulunamadi (esik
                    YOK, cagiran taraf yorumlar - bkz. modul docstring'i).
    matched_parent_name / matched_parent_id: sinira karar verdiren gercek parent kaydi.
    """

    institution_part: str
    unit_part: str
    boundary_score: float
    matched_parent_name: str | None
    matched_parent_id: str | None


def _default_search_fn(text: str, record_type: str) -> list[dict[str, Any]]:
    from institution_resolver_v3.elastic.search import search

    return search(text, record_type, size=5)


def decompose(
    query: str,
    *,
    search_fn: SearchFn = _default_search_fn,
    top_k: int = 5,
) -> DecomposedQuery:
    """Sorguyu kurum/birim kismina ayirir (bkz. modul docstring'i - yontem).

    `search_fn(text, record_type)` her aday kesim noktasi icin cagirilir
    (`record_type="parent"`); testlerde gercek ES yerine sahte bir fonksiyon
    enjekte edilebilir.
    """
    surface_tokens = expand_query_text(query).split()
    if not surface_tokens:
        return DecomposedQuery(
            institution_part=query, unit_part="", boundary_score=0.0,
            matched_parent_name=None, matched_parent_id=None,
        )

    norm_tokens = [normalize(tok).base_no_accent for tok in surface_tokens]

    best_score = -1.0
    best_i = len(surface_tokens)
    best_name: str | None = None
    best_id: str | None = None

    for i in range(1, len(surface_tokens) + 1):
        candidate_surface = " ".join(surface_tokens[:i])
        candidate_norm = " ".join(norm_tokens[:i])
        hits = search_fn(candidate_surface, "parent")[:top_k]
        for hit in hits:
            hit_norm = normalize(hit.get("name", "") or "").base_no_accent
            score = fuzz.ratio(candidate_norm, hit_norm)
            if score >= best_score:  # >= : esitlikte daha UZUN parcayi tercih et
                best_score = score
                best_i = i
                best_name = hit.get("name")
                best_id = hit.get("id")

    institution_part = " ".join(surface_tokens[:best_i])
    unit_part = " ".join(surface_tokens[best_i:])
    return DecomposedQuery(
        institution_part=institution_part,
        unit_part=unit_part,
        boundary_score=max(best_score, 0.0),
        matched_parent_name=best_name,
        matched_parent_id=best_id,
    )
