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

KARAR DEGIL HIPOTEZ (2026-07-23 revizyonu)
------------------------------------------
decompose TEK sinir SECMEZ - farkli parent'lara isaret eden en iyi
MAX_HYPOTHESES sinir hipotezini birlikte dondurur (`hypotheses`, skor sirali;
birincil alanlar = hypotheses[0], geriye donuk uyumlu). Neden: fuzz.ratio
salt karakter benzerligi - kisa+tesadufi ortusme, uzun+dogru parcayi
gecebiliyor (kanitli ornek: "Department of Educational" penceresi, alakasiz
"Department of Education" (K. Irlanda) kaydina 95.8 alip dogru cevabi
"Hacettepe University"yi (90.5) yendi - bkz.
docs/DENEY_2026-07-23_parent_dogrulama.md). Tek sert karar bu hatayi zincirin
sonuna tasiyordu; hipotez listesi ile SECIMI asagi katmanlar (recall-yonelimli
birlesim -> LLM hakem) yapar, decompose hatasi olumcul olmaktan cikip havuza
gurultu eklemekle sinirlanir. Ayni gun denenen "decompose icinde subunit
kanitiyla dogrulama/secim" yaklasimi 50 sorguluk testte yeni yanlilik ekledigi
icin geri alinmisti - hipotezler SIRALANIR ama burada asla ELENMEZ/yeniden
secilmez, o deneyin tuzagi tekrarlanmaz.

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

from dataclasses import dataclass, field
from typing import Any, Callable

from rapidfuzz import fuzz

from institution_resolver_v3.normalize.query_pipeline import expand_query_text, normalize

SearchFn = Callable[[str, str], list[dict[str, Any]]]
# (metinler, record_type) -> her metin icin hit listesi (giris sirasiyla hizali)
SearchManyFn = Callable[[list[str], str], list[list[dict[str, Any]]]]


def _name_variants(hit: dict[str, Any]) -> list[str]:
    """Sinir skorunda denenecek ad varyantlari: name + alias'lar + virgul-segmentleri.

    Ham veride bazi alias'lar virgulle birlesmis BIRDEN FAZLA ad tasiyor
    ("Universitaet Muenster, Westfälische Wilhelms-Universität Münster" TEK
    alias - canli dogrulandi, parent:12928); birlesik dizgeye karsi ratio
    dusuk kaldigi icin dogru hipotez dogamiyordu. Segmentler EK varyant olarak
    denenir (butun de kalir). Tek kelimelik segmentler ALINMAZ: "Jastec Co.,
    Ltd. (Japan)" gibi adlardan kopan "Ltd." parcasi, "ltd" iceren sorgularda
    100'luk tesadufi cekim merkezi olurdu (bilinen tuzak sinifi, bkz.
    docs/DENEY_2026-07-23_parent_dogrulama.md).
    """
    out: list[str] = []
    base = [hit.get("name", "") or ""]
    base.extend(hit.get("aliases") or [])
    for v in base:
        if not v:
            continue
        out.append(v)
        if "," in v:
            for seg in v.split(","):
                seg = seg.strip()
                if seg and len(seg.split()) >= 2:
                    out.append(seg)
    return out

# Farkli parent'lara isaret eden en fazla kac sinir hipotezi dondurulur
# (bkz. modul docstring'i "KARAR DEGIL HIPOTEZ").
# 3 -> 5 (2026-07-23): alias-farkindalikli skorla tek-tokenlik pencereler
# akronim alias'larina tesadufen 100 alabiliyor ("Ana" -> "ANA Aeroportos",
# canli dogrulandi) ve dogru coklu-token hipotezini (~86) top-3 disina
# itebiliyor. "Akronim gercek mi tesadufi mi" ayrimi formdan yapilamaz - o
# secim LLM hakemin isi; burada tek gorev dogru hipotezi LISTEDE TUTMAK.
MAX_HYPOTHESES = 5


@dataclass
class BoundaryHypothesis:
    """Tek bir sinir hipotezi: 'kurum kismi bu aralik olabilir' + kanit.

    institution_part / unit_part: bu hipoteze gore bolme.
    boundary_score: rapidfuzz.fuzz.ratio (0-100) - hipotezin kaniti.
    matched_parent_name / matched_parent_id: hipotezi ureten gercek parent kaydi.
    """

    institution_part: str
    unit_part: str
    boundary_score: float
    matched_parent_name: str | None
    matched_parent_id: str | None


@dataclass
class DecomposedQuery:
    """Sorgu ayristirma sonucu.

    hypotheses: farkli parent'lara isaret eden en iyi MAX_HYPOTHESES sinir
                hipotezi, skor sirali (esitlikte uzun aralik, sonra ilk
                gorulen). SECIM burada yapilmaz - tuketici (resolve/LLM hakem)
                hipotezlerin hepsini degerlendirir.
    institution_part / unit_part / boundary_score / matched_parent_*:
                birincil (en guclu) hipotezin kopyasi - geriye donuk uyumlu
                kisayol; hypotheses[0] ile her zaman ayni.
    """

    institution_part: str
    unit_part: str
    boundary_score: float
    matched_parent_name: str | None
    matched_parent_id: str | None
    hypotheses: list[BoundaryHypothesis] = field(default_factory=list)


def _default_search_fn(text: str, record_type: str) -> list[dict[str, Any]]:
    from institution_resolver_v3.elastic.search import search

    return search(text, record_type, size=10)


def _default_search_many_fn(texts: list[str], record_type: str) -> list[list[dict[str, Any]]]:
    from institution_resolver_v3.elastic.search import search_many

    return search_many(texts, record_type, size=10)


def decompose(
    query: str,
    *,
    search_fn: SearchFn = _default_search_fn,
    # Coklu-metin arama: tum span'ler TEK msearch round-trip'inde (O(n^2) span,
    # eskiden n(n+1)/2 sirali HTTP -> tek istek). Sonuc span-basina search_fn'e
    # BYTE-DENK; sadece varsayilan (gercek ES) yolda devrede. `search_fn` OZEL
    # enjekte edildiyse (testler) None birakilir -> span-basina o fn cagrilir,
    # eski davranis birebir korunur.
    search_many_fn: SearchManyFn | None = None,
    # 5 -> 10 (2026-07-23): kisa fuzzy-junk adlar ("Jastec"), alan-uzunlugu normu
    # yuzunden dogru kaydin exact-alias eslesmesini ("JAMSTEC" @ rank 7,
    # "University of Münster" @ rank 6) top-5 disina itebiliyor - canli olculdu.
    # Ek ES cagrisi yok, sadece pencere basina daha fazla ucuz fuzz.ratio.
    top_k: int = 10,
) -> DecomposedQuery:
    """Sorguyu kurum/birim kismina ayirir (bkz. modul docstring'i - yontem).

    Aday kesim noktalari (span'ler) icin parent araması yapilir. Uretimde tum
    span'ler tek `msearch`'te toplanir (`search_many_fn`); testlerde `search_fn`
    enjekte edilirse span-basina o cagrilir (eski sozlesme).
    """
    surface_tokens = expand_query_text(query).split()
    if not surface_tokens:
        return DecomposedQuery(
            institution_part=query, unit_part="", boundary_score=0.0,
            matched_parent_name=None, matched_parent_id=None, hypotheses=[],
        )

    norm_tokens = [normalize(tok).base_no_accent for tok in surface_tokens]
    n = len(surface_tokens)

    # Batch arama: OZEL search_fn enjekte edilmediyse varsayilan msearch; aksi
    # halde (testler / cagiran kendi fn'ini verdi) span-basina o fn'e dus.
    if search_many_fn is None:
        if search_fn is _default_search_fn:
            search_many_fn = _default_search_many_fn
        else:
            search_many_fn = lambda texts, rt: [search_fn(t, rt) for t in texts]  # noqa: E731

    # Span'ler ESKI ile AYNI sirada (start dis, end ic) - `order` sayaci ve
    # esitlik-bozma bu sirayla ozdes kalsin.
    spans = [(start, end) for start in range(n) for end in range(start + 1, n + 1)]
    span_results = search_many_fn([" ".join(surface_tokens[s:e]) for s, e in spans], "parent")

    # Parent basina EN IYI (skor, esitlikte uzun aralik, esitlikte ilk gorulen)
    # aday aralik tutulur - tek global kazanan yerine hipotez havuzu.
    # deger: (score, length, order, start, end, name)
    best_by_parent: dict[str, tuple[float, int, int, int, int, str | None]] = {}
    order = 0

    for (start, end), hits_all in zip(spans, span_results):
        length = end - start
        candidate_norm = " ".join(norm_tokens[start:end])
        hits = hits_all[:top_k]
        for hit in hits:
            pid = hit.get("id")
            if pid is None:
                continue
            # Skor = name + HER alias'a karsi ayri ayri fuzz.ratio'nun en iyisi.
            # Kanitli kacak sinifi (30-sorgu duman testi, 2026-07-23): sorgu
            # Ingilizce ad/akronimle gelir ("JAMSTEC", "Westfälische
            # Wilhelms-Universität"), kayit farkli kanonik adla durur - ES
            # aliases_text'ten bulur ama name-ratio dusuk kalinca hipotez
            # dogamiyordu. Alias'lar TEK TEK karsilastirilir (uzunluk-duyarli
            # ratio korunur); birlesik metne partial_ratio KULLANILMAZ
            # (jenerik pencere tuzagi - bkz. mappings.py "aliases" notu).
            score = max(
                fuzz.ratio(candidate_norm, normalize(v).base_no_accent)
                for v in _name_variants(hit)
            )
            cur = best_by_parent.get(pid)
            # esitlikte DAHA UZUN araligi tercih et (bilesik ad durumu)
            if cur is None or score > cur[0] or (score == cur[0] and length > cur[1]):
                best_by_parent[pid] = (score, length, order, start, end, hit.get("name"))
                order += 1

    if not best_by_parent:
        return DecomposedQuery(
            institution_part=" ".join(surface_tokens), unit_part="",
            boundary_score=0.0, matched_parent_name=None, matched_parent_id=None,
            hypotheses=[],
        )

    # Siralama global kazanan mantigiyla ayni: skor > uzunluk > ilk gorulen.
    ranked = sorted(
        best_by_parent.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[1][2])
    )[:MAX_HYPOTHESES]

    hypotheses = [
        BoundaryHypothesis(
            institution_part=" ".join(surface_tokens[start:end]),
            unit_part=" ".join(surface_tokens[:start] + surface_tokens[end:]),
            boundary_score=max(score, 0.0),
            matched_parent_name=name,
            matched_parent_id=pid,
        )
        for pid, (score, _length, _order, start, end, name) in ranked
    ]

    primary = hypotheses[0]
    return DecomposedQuery(
        institution_part=primary.institution_part,
        unit_part=primary.unit_part,
        boundary_score=primary.boundary_score,
        matched_parent_name=primary.matched_parent_name,
        matched_parent_id=primary.matched_parent_id,
        hypotheses=hypotheses,
    )
