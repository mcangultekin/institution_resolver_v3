# ingest/ + normalize/ — analiz (2026-07-29)

Kapsam: `ingest/raw_loader.py`, `ingest/canonicalize.py`, `ingest/build.py`,
`normalize/query_pipeline.py`, `normalize/abbreviations.py`,
`normalize/qualifiers.py`, `normalize/text_eski.py`, `models.py`.

Kanıt: **[Ö]** ölçüldü · **[K]** kod okumasıyla kesin · **[V]** muhakeme.

---

## 1. Rol ve genel değerlendirme

`ingest/` ham CSV'yi (106.332 parent / 179.121 subunit satırı) kanonik JSONL'e
çevirir; `normalize/` tüm sistemin metin eşleşme zeminini kurar.

**Bu iki katman projenin en sağlam bölümü.** Gerekçeler:

- `raw_loader` ↔ `canonicalize` ayrımı temiz: okuma tarafında sıfır iş mantığı,
  iş mantığı tarafında sıfır I/O. Her P adımı yan-etkisiz ve `(sonuç, StepStats)`
  döndürüyor — rapor üretimi mantığa sızmamış.
- Adım sırası bağımlılığı **açıkça belgelenmiş ve doğru**: P3'ün merge anahtarı
  qualifier soyma öncesi ada göre kuruluyor, yoksa (İÖ) ikizleri ve tezli/tezsiz
  yanlış birleşirdi (`canonicalize.py:17-19`).
- P3 birleşme anahtarına **alias değer kümesi** dahil edilmiş — over-merge geri
  dönülemez bilgi kaybı olacağı için bilinçli olarak muhafazakâr davranılmış.
- `p4_parse_kind_label` bilinmeyen bir `kind_label` gördüğünde sessiz geçmiyor,
  rapora yazıyor — konvansiyon değişim dedektörü.
- `normalize/query_pipeline.py` iki **gerçek ve sessiz** hata sınıfını çözüyor:
  Türkçe İ/I küçültme hatası ve görünmez karakterler (NBSP/ZWSP/BOM). İkisi de
  exception fırlatmaz, sadece yanlış sonuç üretir — tam olarak merkezîleştirilmesi
  gereken şeyler.
- `locale_aware_lower` kaynak `locale` etiketine değil **içerik kanıtına** bakıyor;
  gerekçe ölçülmüş (locale="tr" etiketli 39.175 kaydın açıkça İngilizce olduğu).

Aşağıdaki eksikler bu tabloyu değiştirmiyor — çoğu kenar durumu.

---

## 2. Eksikler

### E1 — İki normalizasyon kanalı apostrofta ayrışıyor **[Ö]**

Sistemde metin **iki farklı yoldan** tokenlere ayrılıyor:

| Kanal | Nerede | "Gazi'nin" → |
|---|---|---|
| ES analyzer (`apostrophe` filtresi) | BM25 retrieval | `gazi` |
| `normalize().base_no_accent` | `exact_match`, `decompose`, P2/P3 anahtarları | `gazi nin` |

`clean_punctuation` apostrofu boşluğa çeviriyor, ES'in `apostrophe` filtresi ise
apostroftan **sonrasını atıyor**. Ölçüm:

- 2.681 parent adı apostrof içeriyor.
- `normalize()` sonrası **1.692 parent adında yalnız başına `s` token'i** oluşuyor
  (`"St. Michael's Hospital"` → `st michael s hospital`).

Sonuç: bu kayıtlar için `retrieve._contains_exact` (yani gate'in karar omurgası)
sorguda `michael s hospital` dizisini arıyor. Kullanıcı apostrofsuz yazdığında
(`"St Michaels Hospital"` → `st michaels hospital`) exact **hiç ateşlemiyor**,
oysa BM25 tarafı kaydı rahatça buluyor. Yani exact_match'in ıskaladığı bir vaka
sınıfı doğrudan buradan doğuyor.

**Öneri:** `clean_punctuation`'dan önce apostrof-eki soyma (`'…` → sil) ekleyip
iki kanalı hizala. Tek regex, `normalize()` içinde, ES tarafına dokunmadan.

### E2 — Kısaltma genişletmesinde noktasız formlar ölçülmemiş **[Ö]**

`abbreviations.py` docstring'i frekansları **noktalı** formlar için raporluyor
(`FAC. (74)`, `INST. (38)`, `DEPT. (14)`, `ENG. (106)`), ama regex'ler noktayı
opsiyonel yapıyor (`\bFAC\.?\b`) — yani noktasız token'de de ateşliyorlar.

Korpus taraması (231.291 kayıt) — gerçek etki **çok küçük**:

```
NOKTASIZ 'ARS'  -> ARAŞTIRMA   3 kayıt   ("Ars Electronica Center" -> "ARAŞTIRMA Electronica Center")
NOKTASIZ 'YO'   -> YÜKSEKOKULU 3 kayıt   ("Yo San University" -> "YÜKSEKOKULU San University")
NOKTASIZ 'MRK'  -> MERKEZİ     1 kayıt
NOKTASIZ 'DEPT' -> DEPARTMENT  1 kayıt
```

Toplam 8 kayıt. **Bu bir öncelik değil** — ama sorgu tarafı ölçülmedi ve orada
serbest metin geldiği için oran farklı olabilir. Kayda geçsin diye yazıyorum;
düzeltme değeri düşük, dokümantasyon borcu ise gerçek (docstring ölçtüğü şeyden
daha geniş bir davranışı anlatıyor).

### E3 — `is_evening` her zaman `False`, `raw_normalized_name` her zaman kopya **[K]**

P5/P6 kullanıcı kararıyla atlandığı için `build.py:58` `is_evening=False` sabit
yazıyor, `raw_normalized_name = normalized_name`. Bu alanlar:
- `models.SubunitCanonical`'da tanımlı,
- `elastic/document.py:66` ile ES'e yazılıyor,
- `elastic/mappings.py:104` ile indeksleniyor,
- hiçbir yerde **okunmuyor**.

Projenin kendi ilkesi (`config/default.yaml` başlığı: "okunmayan ölü anahtar
bırakma"). İki seçenek: ya İÖ tespiti gerçekten yapılsın (bilgi zaten
`qualifiers.py`'de var — `_MODALITY_PATTERNS` `ikinci_ogretim` çıkarıyor), ya da
alan şemadan düşsün. Şu anki hali "var ama hep yanlış" — en kötü seçenek.

### E4 — P2 devir hedefi `min(id)` ile seçiliyor **[K]**

`canonicalize.py:136`: birden fazla aktif parent adayı varsa hedef
`min(cand, key=int)`. Yani **en küçük id** kazanıyor — semantik bir kriter değil,
kayıt yaşı vekili. Ölçülen gerçek veride yalnız 1 devir olduğu için (151 inaktif
→ 147 düşür, 1 devir, 3 muaf) pratikte zararsız; ama `_token_contains` gevşek
eşleşme yaptığı için (`"bilkent universitesi"` ⊂ `"ihsan dogramaci bilkent
universitesi"`) yeni bir dump'ta birden fazla aday çıkabilir ve seçim sessizce
keyfî olur. En azından ambiguity rapora (`StepStats.notes`) yazılmalı.

### E5 — P2 `_token_contains` yönü tek taraflı **[K]**

Kural: inaktif adın, aktif adın **içinde** geçmesi. Ters yön (aktif ad, inaktif
adın içinde — "X Üniversitesi" inaktif, "X" aktif) kapsanmıyor. Veride bu durum
çıkmadı, ama kuralın asimetrisi belgelenmemiş.

### E6 — `text_eski.py` ölü kod **[K]**

49 satır, docstring'i "KULLANILMIYOR, yeni kodda kullanma" diyor. Hiçbir yerden
import edilmiyor. Silinmeli — referans değeri git geçmişinde zaten var.

### E7 — Test boşlukları **[Ö]**

`normalize/abbreviations.py` ve `ingest/build.py` için **hiç test yok**
(testlerde import edilmiyorlar). `abbreviations.py` regex yoğun ve E2'de görülen
tipte kenar davranışları var — burası test edilmeden değiştirilmesi riskli bir
dosya.

---

## 3. Öneriler (öncelik sırasıyla)

1. **E1 (apostrof hizalama)** — tek regex, ölçülebilir kazanç (1.692 kayıt),
   exact_match'in ıskaladığı bir sınıfı doğrudan kapatır. En yüksek değer/maliyet
   oranı.
2. **E3 (`is_evening`)** — ya doldur ya sil. `qualifiers.extract_qualifiers` zaten
   `ikinci_ogretim` üretiyor, doldurmak ucuz.
3. **E7 (abbreviations testi)** — değiştirmeden önce kilitle.
4. **E6 (`text_eski.py` sil)** — 1 dakika.
5. E2/E4/E5 — belgeleme borcu; kod değişikliği gerekmiyor, docstring'ler
   ölçülenle anlatılanı hizalasın.

## 4. Değiştirilmemesi gerekenler

- P adımlarının sırası ve P3'ün soyma-öncesi merge anahtarı — gerekçesi ölçülü
  ve doğru.
- P3'ün alias-farkındalıklı muhafazakârlığı (193 Bankacılık kaydı ayrı kalıyor).
- `locale_aware_lower`'ın içerik-kanıtı yaklaşımı.
- `normalize()` adım sırası (kısaltma genişletme **küçültmeden önce**, çünkü
  regex'ler noktaya dayanıyor) — `normalize.py:214-227` bunu açıkça yazmış.
