# elastic/ + embedding/ — analiz (2026-07-29)

Kapsam: `elastic/client.py`, `mappings.py`, `document.py`, `indexer.py`,
`search.py`, `embedding/encoder.py`, `query_encoder.py`, `text_builder.py`.

Kanıt: **[Ö]** ölçüldü · **[K]** kod okumasıyla kesin · **[V]** muhakeme.

> **2026-07-30 güncellemesi — parent arama kanalı değişti.**
> Bu analiz 29 Temmuz'daki koda ait. O günden sonra parent araması **tek kanala**
> indirildi: nested `alias_variants` (`score_mode: max`), yani kanonik ad ile
> alias arasında **ayrım yok** — bütün yazımlar tek ortak havuzda, her biri ayrı
> nested belge. `name` ve birleşik `aliases_text` parent sorgusundan çıkarıldı
> (`_PARENT_FIELDS` sabiti tamamen kaldırıldı). **Subunit dokunulmadı.**
> Ölçüm (200 kurum, canlı index): alias ile arama top1 %47→%84.5, top10
> %70.5→%99.5, havuz dışı %11→%0.5; kanonik ad %98.5→%100.
> Aşağıdaki bulgulardan **E7 kısmen ele alındı** (parent'ta `most_fields`
> toplaması ve birleşik alanın uzunluk-normu dezavantajı kalktı; `fuzziness: AUTO`
> her terime uygulanmaya **devam ediyor** ve o kısım hâlâ açık). **E1, E2, E3,
> E4, E5, E6, E8, E9 aynen geçerli.** Gerekçe ve ara varyant ölçümleri:
> `search.py` `_alias_variants_clause` docstring'i; karar kaydı: `docs/DURUM.md`.

---

## 1. Rol ve genel değerlendirme

Arama altyapısı. Tek ES index'i (`institutions_v1`) hem parent hem subunit
taşıyor, `record_type` sorgu-zamanı filtresiyle ayrılıyorlar.

**Doğru bulduğum kararlar:**

- **TEK index + `record_type` filtresi.** v2'nin iki-index IDF zehirlenmesini
  (parent korpusunda nadir olan "fakültesi" suni-yüksek IDF alıp "ankara tıp
  fakültesi"yi hastaneye götürüyordu) yapısal olarak çözüyor. Doğru katmanda
  verilmiş bir karar.
- **`_id` = `"{record_type}:{id}"`.** Parent ve subunit id uzayları 55.431 kayıtta
  çakışıyor; önek olmasa kayıtlar birbirini ezerdi (`indexer.py:74-76`). Gerçek id
  `_source.id`'de korunuyor, arama onu döndürüyor. Sessiz veri kaybını önleyen
  kritik bir detay.
- **Belge-tarafı folding ES'e bırakılmış** — biz önden agresif normalize etmiyoruz,
  index ve sorgu analyzer'ları simetrik çalışıyor.
- **`aliases` alanı `index: False, doc_values: False`** — aramayı **subunit'te**
  `aliases_text`, **parent'ta** nested `alias_variants` yapıyor (bkz. aşağıdaki
  "2026-07-30 güncellemesi"); ayrı liste yalnızca `decompose`'un alias-başına
  `fuzz.ratio` hesaplayabilmesi için `_source`'ta duruyor. Birleşik metne
  `partial_ratio` uygulamama gerekçesi (jenerik pencere tuzağı) ölçülmüş.
- **Determinizm**: `sort: [_score desc, id asc]`, force-merge 1 segment,
  `rrf_merge`'de skor sonrası id ile tie-break. Gün-1'den düşünülmüş.
- **`search_many`** msearch optimizasyonu: sonucun `[search(t) for t in texts]`
  ile bayt-denk olduğu, farkın yalnız N HTTP → 1 istek olduğu docstring'de
  açıkça iddia edilmiş; alt-sorgu hatasında boş liste dönerek izolasyon
  sağlıyor.
- **`OllamaClient`/encoder model cache'leri** ve `e5` query/passage önek ayrımı
  doğru kurulmuş.

---

## 2. Eksikler

### E1 — Türkçe stemmer YOK **[Ö/K]**

`mappings.py` analyzer filtreleri:

```
turkish_analyzer : apostrophe, turkish_lowercase, turkish_stop
ascii_analyzer   : apostrophe, turkish_lowercase, asciifolding
edge_analyzer    : + edge_ngram
```

**Hiçbirinde stemmer yok.** Türkçe sondan eklemeli bir dil: `üniversite`,
`üniversitesi`, `üniversitesinin`, `üniversiteye` BM25 için **farklı token'lar**.
Şu an bunu tek kurtaran `multi_match`'in `fuzziness: "AUTO"`'su
(`universite` ↔ `universitesi` düzenleme mesafesi 2, AUTO uzun kelimede 2'ye izin
verir) — yani morfoloji, **fuzzy'nin yan etkisiyle** tesadüfen kısmen çalışıyor,
tasarlanmış bir çözümle değil. Uzun eklerde (`üniversitesinin`, mesafe 5) fuzzy
de yetmez.

**Bu, gate raporundaki "P1 morfoloji" maddesinin gerçek adresi.** DURUM §6e'de P1
"bu sette 0 vaka" diye ertelenmişti; doğru tespit, ama ertelenen iş gate'e ait
değil — buraya ait. ES `snowball`/`turkish` stemmer'ı ya da `kp` filtresi tek
satırlık bir analyzer değişikliği; maliyeti **yeniden indeksleme**.

⚠️ Ölçülmeden yapılmamalı: stemmer aynı zamanda ayırt ediciliği düşürür
(`tıp`/`tıbbi` aynı köke iner). Önce A/B: aynı 50 sorgu, stemmerli/stemmersiz
index, recall@k farkı.

### E2 — `edge_ngram` indeksleniyor ama HİÇ sorgulanmıyor **[Ö]**

`mappings._text_field()` her `name` ve `parent_name` alanına bir `.edge` alt-alanı
veriyor (`edge_ngram`, `min_gram=2, max_gram=20`). Ama `search.py`'nin sorgu alan
listeleri:

```python
# 2026-07-30 ONCESI (bu analiz o gune ait):
_PARENT_FIELDS  = ["name^2.2", "name.ascii^1.5", "aliases_text^2", "aliases_text.ascii^1.3"]
_SUBUNIT_FIELDS = ["name^3", "name.ascii^2", "aliases_text^1.5", "aliases_text.ascii",
                   "parent_name^1.5", "parent_name.ascii"]

# 2026-07-30 SONRASI: _PARENT_FIELDS KALDIRILDI, parent tek kanala indi
_PARENT_ALIAS_VARIANT_FIELDS = ["alias_variants.value^2", "alias_variants.value.ascii^1.3"]
# _SUBUNIT_FIELDS aynen duruyor
```

`.edge` **hiçbir sorguda geçmiyor** (grep ile doğrulandı — `search.py`'de "edge"
kelimesi hiç yok). Yani 285K belge × 2 alan için 2–20 karakterlik tüm önekler
indeksleniyor, disk ve indeksleme süresi harcanıyor, karşılığında sıfır sorgu
değeri alınıyor. `normalized_name` keyword alanı da aynı durumda —
tanımlı, doldurulmuş, hiç sorgulanmıyor.

**Öneri:** ya `.edge`'i sorgu alanlarına düşük boost'la ekle (kısmi/önek yazan
kullanıcı için — orijinal amaç buydu), ya da mapping'den kaldır. Şu anki hali
her iki dünyanın maliyeti, hiçbirinin faydası.

### E3 — Config'teki boost değerleri KODLA ALAKASIZ **[Ö]**

`config/default.yaml`:

```yaml
retrieval:
  boosts:
    unit_name: 3.0
    unit_name.ascii: 2.0
    aliases.normalized: 1.5
    parent_name: 1.0
```

- `boosts` anahtarı `src/` içinde **hiç okunmuyor** (grep: 0 hit).
- Değerler `search.py`'de sabit yazılı ve **farklı** (`parent_name^1.5`, config
  `1.0` diyor).
- Alan adları mapping'de **yok**: `unit_name` ve `aliases.normalized` diye alanlar
  yok — gerçek adlar `name` ve `aliases_text` (2026-07-30 sonrası parent'ta
  `alias_variants.value`). Bu blok **v2 şemasından kalma**.

Sonuç: bu dosyada boost ayarlayan biri hiçbir etki göremez ve neden göremediğini
anlamaz. Aynı durum `pool_size`, `parent_top_k`, `subunit_top_k`,
`rrf.rank_constant` için de geçerli (hepsi 0 hit). Ayrıntı: `07_api_cli_config.md`.

### E4 — Embedding cache anahtarı içerik değil, id listesi **[K]**

`indexer._compute_embeddings`:

```python
if cache_path and Path(cache_path).exists():
    data = np.load(cache_path, allow_pickle=True)
    if list(data["ids"]) == ids:
        return data["vecs"].tolist()
```

Cache geçerlilik kontrolü **yalnız id sırası**. Ama embed metni
`build_embed_text(r, parent_names)` ile üretiliyor ve şunlara bağlı: kaydın adı,
alias'ları, **ve subunit için parent'ın adı**.

Somut kırılma: bir parent'ın adı düzeltilir (id değişmez) → o parent'ın altındaki
tüm subunit'lerin embed metni değişir → ama id listesi aynı kaldığı için
`embeddings.npz` **sessizce eski vektörleri döndürür**. Yeniden indeksleme
"başarılı" görünür, vektörler bayattır. Sessiz yanlış sonuç — projenin en çok
kaçınmaya çalıştığı hata sınıfı.

Ek olarak `ids` listesi parent+subunit birleşimi ve bu iki uzay 55.431 id'de
çakışıyor, yani listede tekrarlar var — `record_type` cache anahtarında yok.

**Öneri:** cache anahtarına embed **metinlerinin** hash'ini ekle
(`hashlib.sha256("\n".join(texts))`) — bir satır, tüm sınıfı kapatır.

### E5 — Vektör↔belge eşleşmesi iki fonksiyon arası pozisyona bağlı **[K]**

`index_data` embeddings'i `parents + subunits` sırasıyla hesaplıyor;
`_actions` ayrı bir fonksiyonda yine `parents + subunits` kurup
`embeddings[i]` ile eşliyor. İki yerde tekrarlanan, tip sistemiyle korunmayan
bir sıralama sözleşmesi. Biri değişirse vektörler **yanlış belgelere** bağlanır ve
hiçbir hata alınmaz (boyut aynı kalır). Dict (`{f"{rt}:{id}" -> vec}`) ile
eşlemek riski sıfırlar.

### E6 — `index_data(recreate=True)` varsayılan **[K]**

Varsayılan davranış index'i **siler ve yeniden kurar**. `inres3 index` komutunun
yanlışlıkla çalıştırılması üretim index'ini uçurur. Varsayılan `False` olup
`--recreate` açık bayrak olmalı.

### E7 — `fuzziness: AUTO` her terime, `most_fields` ile birlikte **[V]**

`build_search_query` tüm terimlere fuzzy uyguluyor. Bu, gate raporundaki "kısa
jenerik çöp adaylar havuza giriyor" gözlemini besleyen kaynaklardan biri:
`"india"` gibi kısa bir kayıt, uzun bir sorgudaki herhangi bir 1-2 mesafeli
token'la eşleşip havuza giriyor. `most_fields` skorları alanlar arasında
**topladığı** için çok alanlı kayıtlar ayrıca avantajlı.

Ölçülmedi — ama `fuzziness`'ı daralmak ya da `prefix_length: 1` eklemek ucuz bir
deney. Havuz kalitesi gate'in tsr tabanını doğrudan etkiliyor (bkz. `01_gate.md` A2).

**2026-07-30 kısmi çözüm:** parent artık tek alan çiftiyle (`alias_variants.value`
+ `.ascii`) arandığı için "çok alanlı kayıt avantajı" parent tarafında kalktı;
birleşik `aliases_text`'in uzunluk-normu dezavantajı da gitti. `fuzziness: AUTO`
her terime uygulanmaya **devam ediyor** — E7'nin bu yarısı hâlâ açık ve kısa
jenerik adayların havuza girmesini beslemeye devam ediyor. Subunit'te E7 tamamen
geçerli (alan listesi değişmedi).

### E9 — ES'te 3.7 GB v2 artığı duruyor **[Ö, 2026-07-29 eklendi]**

Canlı ES'te üç index var:

```
institutions_v1        231.291 kayıt   3.5 GB   ← v3'ün kullandığı (config bunu gösteriyor)
institutions_parent    493.552 kayıt   1.6 GB   ← v2 artığı
institutions_subunit   454.837 kayıt   2.1 GB   ← v2 artığı
```

Son ikisi, v3'ün açıkça terk ettiği **iki-index** tasarımından kalma — bu raporun
en başında anlatılan IDF zehirlenmesinin kaynağı olan yapı. v3 kodunda bu iki ad
hiç geçmiyor (grep: 0 hit), yani ölü ağırlık. Silinirse 3.7 GB kazanılır.

⚠️ v2 hâlâ kullanımdaysa o projeyi bozar — silmeden önce teyit gerekir.

### E8 — Test boşluğu **[Ö]**

`elastic/indexer.py`, `elastic/client.py`, `embedding/encoder.py`,
`embedding/query_encoder.py` için hiç test yok. E4/E5 gibi sessiz-yanlış
sınıfları tam olarak testsiz bölgede.

---

## 3. Öneriler (öncelik sırasıyla)

| # | İş | Neden | Maliyet |
|---|---|---|---|
| 1 | **E4** cache anahtarına metin hash'i | sessiz bayat vektör riski | 1 satır |
| 2 | **E5** vektörü id-dict ile eşle | sessiz yanlış eşleşme riski | ~10 satır |
| 3 | **E6** `recreate` varsayılanı `False` | veri kaybı riski | 1 satır |
| 4 | **E3** config boost bloğunu ya bağla ya sil | yanıltıcı ayar yüzeyi | küçük |
| 5 | **E2** `.edge` kararı: bağla ya da kaldır | boşa index maliyeti | reindex |
| 6 | **E1** stemmer A/B deneyi | Türkçe morfolojinin gerçek adresi | reindex + ölçüm |
| 7 | **E7** fuzziness daraltma deneyi | havuz gürültüsü → gate tabanı | küçük + ölçüm |

E1 ve E7'nin ikisi de **ölçüm gerektiriyor** — `06_eval_ve_batch.md`'deki eval
seti (`data/eval/benchmark_500_sample.csv`) üzerinde skorlama kurulmadan bunlara
girilmemeli.

## 4. Değiştirilmemesi gerekenler

- Tek index + `record_type` filtresi (v2 IDF zehirlenmesi çözümü).
- `record_type:id` bileşik `_id` (55.431 çakışma).
- `aliases` alanının aramaya kapalı ama `_source`'ta tutuluyor olması.
- Determinizm üçlüsü (sort tie-break, force-merge, RRF id tie-break).
- Subunit'e parent-adı enjeksiyonu (hem ES belgesinde hem embed metninde).
