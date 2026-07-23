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
Sorgunun her olasi ARDISIK ALT-DIZGESINI dene (sadece 0'dan baslayan onekler
DEGIL - her `(start, end)` araligi: tek kelimeler dahil, tum kombinasyonlar).
Ilk surum sadece onekleri deniyordu ("kurum kismi hep basta" varsayimi) -
bu, birim once yazilan sorgularda ("istatistik bolumu gazi universitesi")
tamamen kirildi: hicbir onek "gazi universitesi"ye tam oturamadigi icin
sinir hic bulunamiyor, tum sorgu tek parca kaliyordu. Alt-dizge taramasi bu
varsayimi da kaldirir - kurum adi sorgunun basinda, sonunda ya da ortasinda
olabilir, hepsi ayni mekanizmayla denenir.

Her aday parca icin ES'te (BM25, ucuz - embedding YOK) en yakin parent'lari
bul, `rapidfuzz.fuzz.ratio` (uzunluk-duyarli DUZ oran - `token_set_ratio`
DEGIL, o fazla/eksik kelimeye goz yumdugu icin siniri ayirt edemiyor, bkz.
asagidaki not) ile aday parcanin bulunan parent adina NE KADAR TAM ORTUSTUGUNU
olc. Hangi aralik bir gercek parent adina neredeyse birebir (~100) uyuyorsa,
kurum siniri orasi - kurum adinin kendisi kadar uzayip kendisinden fazla
uzamiyor. Testlerde (bkz. tests/unit/test_decompose.py) hem Ingilizce "of"
oruntusu hem Turkce bilesik ad hem birim-once hem de "hicbir kurum yok"
durumu (duz skorlarin hicbiri 100'e yaklasmiyor) dogru sekilde ayirt edildi.

`token_set_ratio` DEGIL `ratio` kullanma nedeni: `token_set_ratio` fazla/eksik
kelimeye tolerans gosterir (kesisim tam ise 100 dondurur, adayin FAZLADAN
kelimesi olsa bile) - bu da her kesim noktasinin ayni sekilde 100 almasina
(hicbir ayirt edicilik kalmamasina) yol aciyordu. `ratio` uzunluk farkina
duyarli oldugu icin dogru sinirda net bir PIK olusuyor.

Esiksiz: en yuksek skoru veren aralik secilir (esitlikte DAHA UZUN aralik
tercih edilir - bilesik ad durumunu dogru cozer: "Eskisehir Osmangazi
Universitesi" (kisa aralik) ile "...Universitesi Tip Fakultesi Hastanesi"
(tum sorgu) ayni 100 skoru alabilir, uzun olan kazanir). Hicbir zorlama esik
YOK (esik tahmini icin etiketli set gerekiyor, bkz. docs/DURUM.md calisma
tarzi) - dusuk-guven bir bolme bile zarar vermez, cunku cagiran taraf
(retrieve/resolve.py) HER ZAMAN filtresiz aramayi da tutup birlestirir
(recall-guvenli cascade).

Maliyet: n token icin onek-taramasi n ES cagrisi yapiyordu, alt-dizge
taramasi n(n+1)/2 yapar (10 token -> 55 cagri). Sorgular kisa oldugu icin
(<=512 karakter, tipik <=10-15 token) kabul edilebilir; batch olcegindeki
etkisi F5'te olculecek (docs/DURUM.md acik karar).

`unit_part` artik kurum araliginin DISINDA KALAN iki parcanin (once + sonra)
birlesimi olabilir - kurum sorgunun ortasinda bulunursa sira bilgisi
`unit_part` tek dizgesinde kaybolur, ama bu alan zaten sadece CLI
gosterimi/hata ayiklama icin kullaniliyor (resolve() parent aramasi disinda
tuketmiyor).

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
    n = len(surface_tokens)

    best_score = -1.0
    best_length = -1
    best_start = 0
    best_end = n
    best_name: str | None = None
    best_id: str | None = None

    for start in range(n):
        for end in range(start + 1, n + 1):
            length = end - start
            candidate_surface = " ".join(surface_tokens[start:end])
            candidate_norm = " ".join(norm_tokens[start:end])
            hits = search_fn(candidate_surface, "parent")[:top_k]
            for hit in hits:
                hit_norm = normalize(hit.get("name", "") or "").base_no_accent
                score = fuzz.ratio(candidate_norm, hit_norm)
                # esitlikte DAHA UZUN araligi tercih et (bilesik ad durumu)
                if score > best_score or (score == best_score and length > best_length):
                    best_score = score
                    best_length = length
                    best_start = start
                    best_end = end
                    best_name = hit.get("name")
                    best_id = hit.get("id")

    institution_part = " ".join(surface_tokens[best_start:best_end])
    unit_part = " ".join(surface_tokens[:best_start] + surface_tokens[best_end:])
    return DecomposedQuery(
        institution_part=institution_part,
        unit_part=unit_part,
        boundary_score=max(best_score, 0.0),
        matched_parent_name=best_name,
        matched_parent_id=best_id,
    )
