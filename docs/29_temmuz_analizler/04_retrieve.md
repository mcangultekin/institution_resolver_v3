# retrieve/ — analiz (2026-07-29)

Kapsam: `retrieve/decompose.py` (302), `retrieve/resolve.py` (448).
Sistemin **çekirdek yolu** — CLI, API, gate, judge, decide, üç batch türü, hepsi
buradan geçiyor.

Kanıt: **[Ö]** ölçüldü · **[K]** kod okumasıyla kesin · **[V]** muhakeme.

---

## 1. Rol ve genel değerlendirme

`decompose` sorguyu kurum/birim sınırına ayırır (tek karar değil, 5 hipotez);
`resolve` her hipotezle arama yapıp recall-güvenli bir aday havuzu kurar ve her
adaya ham kanıt (sinyal) iliştirir.

**Projenin en iyi düşünülmüş fikri burada:** "kural yazma, veriye sor". Sorguyu
`üniversitesi` gibi bir işaretçide kesmek yerine, sorgunun her ardışık
alt-dizgesi ES'e soruluyor ve hangi aralık gerçek bir parent adına oturuyorsa
sınır orası kabul ediliyor. Reddedilen alternatifin (marker-regex) iki kırılma
noktası da ölçülmüş: İngilizce "University **of** X" ters-örüntüsü (~8.566 kayıt)
ve Türkçe zincirleme bileşik adlar. Dil-özel istisna listelerine sapılmamış.

Diğer güçlü kararlar:
- **KARAR DEĞİL HİPOTEZ** — tek sert sınır kararı hatayı zincirin sonuna
  taşıyordu; hipotez listesiyle decompose hatası "ölümcül" olmaktan çıkıp
  "havuza gürültü" seviyesine iniyor. Kanıtlı örnekle gerekçelendirilmiş.
- **Recall-güvenli birleşim**: subunit hem filtreli hem filtresiz aranıp
  birleştiriliyor — parent tahmini yanlışsa doğru subunit kaybolmuyor, sadece
  sıralamada geriye düşüyor.
- **RRF yalnız havuzlama için** — tek boyutlu skora ezdirilmiyor; gate/judge ayrı
  ayrı değerlendirebilsin diye ham sinyaller (`bm25_norm`, `cosine`,
  `token_set_ratio`, `exact_match`, `qualifier_conflict`) korunuyor.
- `fuzz.ratio` vs `token_set_ratio` seçimi gerekçelendirilmiş (`ratio`
  uzunluk-duyarlı olduğu için doğru sınırda **pik** oluşuyor).
- `_contains_exact` kelime sınırı gözetiyor — naif `in` ile "ana" ⊂ "anadolu"
  tuzağına düşülmemiş.

---

## 2. Eksikler

### E1 — `unit_part`'ın "sadece gösterim" olduğu iddiası artık YANLIŞ **[K]**

`decompose.py:85-89` docstring'i:

> `unit_part` … bu alan zaten sadece CLI gösterimi/hata ayıklama için
> kullanılıyor (resolve() parent araması dışında tüketmiyor).

Bu **artık doğru değil**. `gate.gate()` (`gate.py:223`) `unit_part`'ı okuyor ve
iki karar veriyor:
1. `unit_phrase is None` → subunit havuzu **hiç değerlendirilmiyor** (verdict yok),
2. `_is_short_acronym(unit_phrase)` → subunit `review`'a çekiliyor.

Yani "sıra bilgisi kaybolur ama önemsiz" diye kabul edilen bir alan, sonradan
**karar taşıyan** hale gelmiş ve docstring güncellenmemiş. `unit_part`, kurum
aralığının önündeki + arkasındaki parçaların birleşimi olduğu için:
`"Tıp Fakültesi Ege Üniversitesi Geriatri"` → `unit_part = "Tıp Fakültesi Geriatri"`
(araya kurum girmiş, sıra kaybolmuş). Gate bu birleşik dizgeye akronim testi
uyguluyor.

### E2 — "Sınır bulunamadı" ile "sorguda birim yok" aynı değere çöküyor **[K]**

`decompose` hiçbir parent adayı bulamazsa (`best_by_parent` boş):

```python
return DecomposedQuery(institution_part=" ".join(surface_tokens), unit_part="", ...)
```

`unit_part = ""` → gate `unit_phrase = None` → **`subunit = None`**, yani
"sorguda birim ifadesi YOK" anlamına gelen değer.

Ama gerçek durum bu değil: sorguda birim ifadesi olabilir, decompose sınırı
bulamamıştır. `judge/schema.py` bu iki durumu birinci sınıf olarak ayırıyor
(`subunit=None` ≠ `SubunitDecision(no_match)`) — gate, decompose'un bilgi kaybı
yüzünden bu ayrımı **sessizce** yanlış tarafa düşürüyor. Sonuç: catalog'da
karşılığı olan bir birim, hiç aranmadan yok sayılabilir.

**Öneri:** `DecomposedQuery`'ye açık bir `boundary_found: bool` ekle; gate
"sınır yok" durumunda subunit havuzunu yine değerlendirsin (`unit_phrase`
bilinmiyor ama havuz dolu olabilir).

### E3 — Hipotez sıralamasında `order` "ilk görülen" değil "son güncellenen" **[K]**

`decompose.py:267-269`:

```python
if cur is None or score > cur[0] or (score == cur[0] and length > cur[1]):
    best_by_parent[pid] = (score, length, order, start, end, hit.get("name"))
    order += 1
```

`order`, kaydın **güncellendiği** anda atanıyor ve sayaç artıyor. Docstring
"eşitlikte … sonra ilk görülen" diyor (`DecomposedQuery` sınıf docstring'i), ama
saklanan değer **son güncellemenin** sıra numarası. Erken görülüp geç iyileşen bir
parent, geç görülen bir parent'ın arkasına düşebilir.

Etki: eşit skor + eşit uzunlukta hangi hipotezin **birincil** olacağını
değiştirir. Birincil hipotez `institution_part`'ı belirliyor, o da gate'in akronim
testine ve #6'nın (çıkarılmış) kilidine giriyordu. Küçük ama gerçek bir
determinizm/doküman uyuşmazlığı.

### E4 — Alias sayısı ölçülmemiş bir yanlılık **[V]**

`_name_variants` name + tüm alias'lar + virgül segmentlerini döndürüyor, skor
bunların **maksimumu**. Alias'ı bol bir kaydın 100'e ulaşma şansı, tek adlı bir
kaydınkinden yapısal olarak yüksek. Docstring zaten bilinen bir tuzak sınıfını
anlatıyor ("kısa+tesadüfi örtüşme, uzun+doğru parçayı geçebiliyor" — Department
of Education örneği) ama **varyant sayısı** ekseni ölçülmemiş. `MAX_HYPOTHESES=5`
bunu tolere etmek için var; yine de "kaç varyanttan max alındı" bir sinyal olarak
`BoundaryHypothesis`'e yazılabilir (bedava denetim verisi).

### E5 — `token_set_ratio`'nun tam-sorguya hesaplanması, alt-küme tuzağını miras bırakıyor **[Ö]**

`_attach_signals(query_text=query)` — tsr **tam orijinal sorguya** karşı
hesaplanıyor. Gerekçe doğru ve ölçülü (hipotez parçasına göre hesaplansaydı tek
kelimelik jenerik bir parça alakasız adaylara 100 verirdi — Biruni/Selçuk/Boğaziçi
canlı doğrulandı).

Ama seçilen alternatifin de bir maliyeti var ve ölçülmemiş: `token_set_ratio`,
adayın token'ları sorgunun **alt kümesiyse 100 döndürür**.

```
sorgu: "calcutta institute of engineering and management ... kolkata india"
  "india"                          -> 100.0
  "management"                     -> 100.0
  "indian institute of technology" ->  57.1
```

Bu, gate'in `no_match` tabanını öldüren ve review sinyallerini yanlış adaya
bağlayan şey (bkz. `01_gate.md` A2). Kök neden burada üretiliyor, semptom orada
görünüyor. `bm25_norm` için "sorgu-içi göreli, çöp de 1.0 alıyor" diye verilen
red gerekçesinin **birebir aynısı** tsr için fark edilmemiş.

**Öneri (gate'e dokunmadan):** `ScoredCandidate`'e ikinci bir alan ekle —
`tsr_partial` (uzunluk-duyarlı `fuzz.ratio` ya da `token_sort_ratio`). Mevcut
`token_set_ratio` bozulmaz (judge kalibrasyonu korunur), gate/decide isterse
ayırt edici olanı kullanır.

### E6 — Subunit `bm25_norm`'u iki farklı aramanın maksimumuyla normalize ediliyor **[K]**

```python
max_bm25 = max(s_max_bm25, sf_max_bm25)   # filtresiz ve filtreli aramaların max'ı
```

Parent tarafında her arama **kendi içinde** normalize ediliyor (doğru, docstring
bunu vurguluyor: "farklı sorgu metinlerinin ham BM25'leri karşılaştırılamaz").
Subunit tarafında iki ayrı aramanın tabanları karıştırılıyor. Karara girmediği
için zararsız — ama **judge prompt'unda gösteriliyor** (`bm25=0.312`), yani modele
tanımı belirsiz bir sayı sunuluyor.

### E7 — Enjekte hipotez adayları gerçek adaylardan ayırt edilmiyor **[K]**

`_parent_union` sonundaki enjeksiyon, hiçbir aramanın top-K'sına girememiş parent'ı
havuza ekliyor (`bm25_norm=0.0`, `cosine` mget ile, `from_hypothesis_only=True`).
Doğru bir recall kararı. Ama `exact_match` bu adaylar için de hesaplanıyor ve
`raw["from_hypothesis_only"]` bayrağı **hiçbir tüketici tarafından okunmuyor**
(gate de, judge/candidates de). Sonuç: BM25 ve kNN'in ikisinin de bulamadığı bir
kayıt, `exact_match` üzerinden `auto_match` alabiliyor.

### E8 — Havuz boyutu üç yerde üç farklı **[Ö]**

| Yer | Değer |
|---|---|
| `config/default.yaml` `retrieval.pool_size` | 50 (**okunmuyor**) |
| `resolve(size=...)` varsayılan | 10 |
| CLI `--top` varsayılan | 5 |
| `search()` varsayılan `size` | 50 |

Gate'in gördüğü havuz aslında 5–10 aday; `pool_size: 50` yorumunda "recall@50 F2'de
ölçülür" yazıyor. Ölçülen şey ile çalışan şey aynı değil.

---

## 3. Öneriler

| # | İş | Neden | Risk |
|---|---|---|---|
| 1 | **E2** `boundary_found` bayrağı | sessizce yok sayılan subunit'ler | düşük, ek alan |
| 2 | **E1** docstring'i düzelt | yanlış "sadece gösterim" iddiası karar taşıyor | sıfır |
| 3 | **E7** `from_hypothesis_only`'yi gate'e taşı | aramada bulunmayan kayıt auto alamasın | gate-lokal |
| 4 | **E5** `tsr_partial` ek alanı | gate'in `no_match` kapısını canlandırır | ek alan, geriye uyumlu |
| 5 | **E3** `order`'ı gerçekten "ilk görülen" yap | determinizm/doküman uyumu | düşük |
| 6 | **E6/E8** normalizasyon ve havuz boyutu tutarlılığı | denetim/ölçüm netliği | düşük |

⚠️ **Kapsam uyarısı:** `resolve.py` çekirdek yol ve `exact_match`/`qualifier_conflict`
doğrudan judge prompt'una gidiyor. DURUM §6e'de kullanıcı kararı net:
*"triyaj sezgileri gate-lokal yapılır; resolve/normalize/judge'a DOKUNULMAZ."*
Yukarıdaki 3/4/5 maddeleri **ek alan** olarak öneriliyor — mevcut alanların
davranışı değişmiyor, judge kalibrasyonu korunuyor. Bu ayrım korunmalı.

## 4. Değiştirilmemesi gerekenler

- Alt-dizge taraması + "veriye sor" yaklaşımı (marker-regex'e dönülmemeli).
- Hipotez listesi (tek sınır kararına dönülmemeli).
- Recall-güvenli filtreli+filtresiz subunit birleşimi.
- RRF'nin yalnız havuzlama için kullanılması.
- `fuzz.ratio` (sınır tespiti) ile `token_set_ratio` (aday sinyali) ayrımı.
- Havuz-msearch birleştirmesi denenip reddedilmiş (~67 ms, çekirdek yol riski) —
  tekrar açılmamalı.
