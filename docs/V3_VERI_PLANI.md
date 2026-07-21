# V3 Veri Yapısı ve İşleme Planı

> Tarih: 2026-07-17. Bu belge, v3 hazırlığında `data/raw/` CSV'lerine uygulanacak
> dönüşümleri ve hedef veri yapısını tanımlar. Buradaki HER sayı bu oturumda ham
> veri üzerinde ölçülmüştür (2026-07-17); "yaklaşık" denmeyen her değer birebir
> ölçümdür. Mimari bağlam için `FABLE_RETROSPEKTIF.md` (özellikle Bölüm 4-5).

---

## 0. Temel ilke: ham CSV'ye dokunulmaz

- `data/raw/institution_parent.csv` ve `institution_subunit.csv` **salt-okunur
  kaynaktır**; hiçbir düzeltme elle CSV üzerinde yapılmaz.
- Tüm dönüşümler tek bir deterministik pipeline'da koşar ve çıktısını
  `data/processed/` altına yazar:
  - `parent_canonical.jsonl`
  - `subunit_canonical.jsonl`
  - `transform_report.json` (her adımın önce/sonra sayıları + istisna listeleri)
- Yeni bir dump geldiğinde aynı pipeline yeniden koşar. Elle düzeltilmiş veri
  diye bir kavram yoktur; her istisna (ör. muaf tutulan inaktif üniversiteler)
  **kodda id listesi olarak değil, kuralla + raporda görünür şekilde** yaşar.
- Kayıt formatı JSONL'dir çünkü kanonik kayıtlar liste alanları taşır
  (`merged_ids`, `aliases`, `name_variants`) — CSV'de JSON-blob gömmek v2'de
  yeterince acı verdi.

---

## 1. Hedef şema

### 1.1 `parent_canonical.jsonl`

```jsonc
{
  "id": "101",                       // ham CSV id'si, string olarak korunur
  "name": "GAZİ ÜNİVERSİTESİ",
  "normalized_name": "gazi universitesi",
  "country": "TR", "city": "Ankara",
  "canonical_ref": "yok:105118",     // dış kimlik; işaretçi DEĞİL (bkz. 2.3)
  "aliases": [ {"value": "...", "locale": "tr", "source": "yok"}, ... ],
  "active_override": false,          // yalnız muaf-inaktifler için true olur
  "record_type": "parent"
}
```

### 1.2 `subunit_canonical.jsonl`

```jsonc
{
  "id": "152006",                    // grubun kanonik (en küçük) id'si
  "merged_ids": ["152006"],          // klon birleşiminden gelen TÜM id'ler (kendisi dahil)
  "parent_id": "101",
  "name": "İSTATİSTİK (YL) (TEZLİ)",
  "normalized_name": "istatistik",   // qualifier'ları soyulmuş çekirdek ad
  "raw_normalized_name": "istatistik (yl) (tezli)",
  "kind_label_raw": "Tezli Yüksek Lisans Programı",

  // kind_label'ın kontrollü ayrıştırması (bkz. 3. bölüm):
  "unit_type": null,                 // bolum | anabilim_dali | bilim_dali | fakulte | ... | null
  "program_type": "tezli_yl",        // lisans | onlisans | tezli_yl | tezsiz_yl | doktora | sanatta_yeterlik | null
  "is_interdisciplinary": false,
  "is_evening": false,               // (İÖ) ikinci öğretim bayrağı
  "is_ror_child": false,

  "hierarchy_context": [],           // zincirli adlardan gelen ara segmentler (ör. ["mühendislik fakültesi"])
  "aliases": [ ... ],                // merge edilen tüm kayıtların alias birleşimi (dedupe'lu)
  "record_type": "subunit"
}
```

Şema `pydantic` ile `extra="forbid"` olarak tanımlanır (REVIEW K-serisi dersi:
sessizce yutulan alan olmasın).

### 1.3 Çıktı sözleşmesine etkisi

Sistemin nihai çıktısı **tek id değil, `{ids: [...], confidence, decision}`**.
`merged_ids` bunun veri tarafındaki temelidir: klon grubuna düşen eşleşmede tüm
grup id'leri döner. Eval kuralı: `expected_id ∈ merged_ids` → doğru.

---

## 2. İşleme adımları (sırayla)

### P1 — Aktif filtre, subunit tarafı: KOŞULSUZ

- 179.106 → **138.298** aktif satır. Düşen 40.808 satırın %99.3'ü eski
  zincirli-ad konvansiyonunun ("ÜNİV, FAKÜLTE, BÖLÜM") artığı ve **hepsinin**
  kind_label'ı boş. Altlarında kimse olmadığı için güvenle düşerler.

### P2 — Aktif filtre, parent tarafı: KOŞULLU (yetim kuralı)

Parent'ta da `active` kolonu var: 106.331 → 106.180 aktif, **151 inaktif**.
Ölçülen gerçek durum:

- `parent_id`'si parent dosyasında hiç olmayan aktif subunit: **0** (FK sağlam).
- İnaktif parent'a bağlı aktif subunit: **52 satır, 4 parent altında**:
  Kıbrıs Sosyal Bilimler Üni (18), Türk-Japon Bilim ve Teknoloji Üni (17),
  Anka Teknoloji Üni (16), Bilkent Üni (1).

Kural:

1. İnaktif parent'ın altında aktif subunit **yoksa** → düşür (147 kayıt).
2. Varsa ve **aynı/kapsayan adla aktif karşılığı varsa** → subunit'lerin
   `parent_id`'si aktif kayda yönlendirilir, inaktif kaydın adı aktif kayda
   alias olarak eklenir. Ölçülen tek örnek: `BİLKENT ÜNİVERSİTESİ` (id=305) →
   `İHSAN DOĞRAMACI BİLKENT ÜNİVERSİTESİ` (id=150). ("Bilkent Üniversitesi"
   zaten insanların yazdığı ad — alias olarak değerli.)
3. Aktif karşılığı **yoksa** → parent `active_override=true` ile korpusta
   kalır ve `transform_report.json`'a düşer. Ölçülen üç örnek: id=118, 356,
   239 — üçü de gerçek, yaşayan üniversiteler; buradaki `active=false`
   muhtemelen kaynak-veri hatası. **Bu id'ler koda gömülmez**; kural her
   koşuda yeniden değerlendirilir.

> ÖNEMLİ (bu oturumda çürütülen fikir): `canonical_ref` bir "doğrusu şu"
> işaretçisi DEĞİLDİR. 151 inaktif parent'ın **0'ı** canonical_ref üzerinden
> aktif bir kayda çözülüyor (Bilkent: inaktif `yok:385964` vs aktif
> `yok:105118`). Yönlendirme ad eşleşmesiyle yapılır, canonical_ref'le değil.

### P3 — Klon birleştirme (planın kalbi)

- Anahtar: **`(parent_id, normalized_name, kind_label)`**.
- Ölçüm: bu anahtarla **5.194 grup, 13.383 fazla satır** (anahtar kind_label'sız
  olsaydı 5.333/13.557 — fark yalnız 174 satır; kind_label'lı anahtar, aynı adlı
  ama farklı türdeki gerçek kayıtları — ör. aynı adın Tezli YL ve Doktora
  programı — yanlışlıkla birleştirmeyi önler).
- En kötü vaka (doğrulandı): SBÜ (parent=49) altında 165× "ALGOLOJİ BİLİM DALI",
  alias'ları dahi birebir aynı.
- İşlem: grup içindeki **en küçük id kanonik olur**, tamamı `merged_ids`'e
  yazılır, alias'lar birleşim + dedupe. Grup üyeleri arasında ayırt edici
  hiçbir alan olmadığı Faz 3.5'te dört ayrı sinyalle kanıtlandı — bu birleşme
  bilgi kaybetmez, verinin gerçek çözünürlüğünü şemaya yansıtır.
- **Yapılmayacak olan**: klonları ayrı kayıt tutup skor/margin tarafında ayırt
  etmeye çalışmak. Bu yol Faz 3.5'te denendi ve kapandı (near-tie yazı-turası,
  Çankırı "TASARIM BÖLÜMÜ" vakası). Geri dönme.

### P4 — kind_label ayrıştırması (24 ham değer → yapılandırılmış alanlar)

Bkz. Bölüm 3'teki tam eşleme tablosu. Ham değer `kind_label_raw`'da korunur.

### P5 — Ad temizliği ve qualifier soyma

- `name` içindeki yapısal parantez qualifier'ları (`(YL)`, `(TEZLİ)`,
  `(TEZSİZ)`, `(DR)`, `(İÖ)`, `PR.` vb.) çekirdek addan soyulur:
  `normalized_name = "istatistik"`, `raw_normalized_name` orijinali korur.
  Soyulan bilgi kaybolmaz — P4'ün yapılandırılmış alanlarına zaten yazılmıştır
  (`program_type=tezli_yl`, `is_evening=true`...). Bu, v2'deki Ö11 (ingest
  qualifier çıkarımı, +3.66pp) işinin şemaya kalıcı taşınmasıdır.
- **(İÖ) ölçümü**: 1.967 aktif kayıt (İÖ) taşıyor ve **%100'ünün** aynı parent
  altında İÖ'süz ikizi var. Kayıtlar ayrı tutulur (`is_evening=true`), karar
  katmanına kural gider: sorgu "ikinci öğretim" qualifier'ı taşımıyorsa İÖ'süz
  kayıt tercih edilir (yumuşak kural; sert birleştirme açık soru — bkz. Bölüm 5).

### P6 — Zincirli ad normalizasyonu

Aktiflerde 2.802 virgüllü zincirli ad var (%2.03). Kural:

- İlk segment kendi parent'ının adı/alias'ıyla eşleşiyorsa **ilk segment
  atılır** (parent-injection'ın parent adını iki kez sokması sorunu; ölçülen
  küme kritere göre ~700–1.200 kayıt, aktiflerin ≤%0.9'u).
- Kalan ara segmentler atılmaz: son segment birincil ad olur, öncekiler
  `hierarchy_context` listesine gider ve embed metnine katılır. Bu, veride
  başka hiçbir yerde olmayan fakülte-katmanı bilgisinin tek kırıntısıdır
  (doğrulandı: hiyerarşi katı iki katman — Beykoz'un "İSTATİSTİK BÖLÜMÜ"nün
  fakülte bağı yok, Gazi'nin 11 istatistik kaydının program↔bölüm bağı yok;
  `parent_id`'si bir subunit'e işaret eden satır sayısı: **0**).

### P7 — Ölü kolonlar

`iz`, `top_iz` şemaya girmez (138K aktif satırda 4 dolu). `created_at`,
`updated_at`, `from_kurum`, `legacy_institution_ids`, `#` de kanonik şemaya
taşınmaz (gerekirse raw'dan her zaman geri okunur).

### P8 — ror_child işaretlemesi

14.957 aktif kayıt (%10.8) `kind_label=ror_child` — yabancı hastane/şirket/
üniversite karışımı. Düşürülmez; `is_ror_child=true` bayrağıyla taşınır.
Şimdilik davranış değişikliği yok; rerank/decide'ın ileride ayrı davranabilmesi
için ucuz bir kapı.

### P9 — Korpus profili (kalıcı)

`transform_report.json` her koşuda şunları içerir ve saklanır:

- Her adımın önce/sonra satır sayısı + düşürülen/birleştirilen id örneklemleri.
- `(parent_id, normalized_name)` kardinalite histogramı (klon nüksü dedektörü).
- Ad-paylaşım histogramı (bugün: aktiflerin %81'i = 112.147 satır adını başka
  satırla paylaşıyor — bu bir veri hatası değil veri doğasıdır; çözümü ingest
  değil, id-listesi çıktı sözleşmesi + parent-koşullu eval'dir).
- Alan doluluk matrisi ve kind_label dağılımı (konvansiyon değişimi dedektörü:
  yeni dump'ta zincirli adlar geri gelirse ya da kind_label boşalırsa kod
  bozulmadan bu rapor söyler).

### Beklenen sonuç (sayısal)

| | v2 (bugün) | v3 processed |
|---|---|---|
| Parent | 106.331 | **106.183** (106.180 aktif + 3 muaf; 305→150'ye devir) |
| Subunit | 179.106 | **124.915** (138.298 aktif − 13.383 klon fazlası) |
| Toplam index | ~285K | **~231K** |

---

## 3. kind_label eşleme tablosu (24 ham değer, tamamı)

İki eksen + iki bayrak: `unit_type` (yapısal birim) ve `program_type` (öğretim
programı) birbirini dışlar; `is_interdisciplinary` ve (addan gelen) `is_evening`
bağımsız bayraklardır.

| Ham değer | n | unit_type | program_type | interdis. |
|---|---|---|---|---|
| Anabilim Dalı | 36.066 | anabilim_dali | – | – |
| Bölüm | 21.421 | bolum | – | – |
| ror_child | 14.957 | ror_child (is_ror_child=true) | – | – |
| Lisans | 13.596 | – | lisans | – |
| Tezli Yüksek Lisans Programı | 11.150 | – | tezli_yl | – |
| Önlisans | 9.375 | – | onlisans | – |
| Bilim Dalı | 7.486 | bilim_dali | – | – |
| Doktora Programı | 6.033 | – | doktora | – |
| Uygulama ve Araştırma Merkezi | 4.088 | uygar_merkezi | – | – |
| Tezsiz Yüksek Lisans Programı | 3.944 | – | tezsiz_yl | – |
| Fakülte | 2.284 | fakulte | – | – |
| Disiplinlerarası Anabilim Dalı | 1.537 | anabilim_dali | – | ✓ |
| Disiplinlerarası Tezli YL Programı | 1.360 | – | tezli_yl | ✓ |
| Meslek Yüksekokulu | 1.104 | myo | – | – |
| Anasanat Dalı | 1.047 | anasanat_dali | – | – |
| Disiplinlerarası Tezsiz YL Programı | 650 | – | tezsiz_yl | ✓ |
| Enstitü | 600 | enstitu | – | – |
| Disiplinlerarası Doktora Programı | 499 | – | doktora | ✓ |
| Sanat Dalı | 372 | sanat_dali | – | – |
| Yüksekokul | 366 | yuksekokul | – | – |
| Rektörlük | 217 | rektorluk | – | – |
| Sanatta Yeterlik Programı | 128 | – | sanatta_yeterlik | – |
| Disiplinlerarası Sanatta Yeterlik Prog. | 10 | – | sanatta_yeterlik | ✓ |
| Disiplinlerarası Anasanat Dalı | 8 | anasanat_dali | – | ✓ |

Bu ayrıştırmanın değeri (Gazi vakasıyla doğrulandı): Gazi altında 11 farklı
"istatistik" kaydı var — Bölüm, Lisans, Tezli/Tezsiz YL (+İÖ ikizleri), DR,
3 ABD, UYG-AR. Bunlar klon DEĞİL; ayırt edici tek yapısal sinyal kind_label
ve v2'de bu kolon index'e hiç girmedi. Sorgu-tarafı qualifier çıkarımı
("tezli", "doktora") doğrudan `program_type` ile eşleşecek.

---

## 4. Nasıl uygulanır

1. **Yeni modül**: `ingest/canonicalize.py` (P1–P8 dönüşümleri, saf fonksiyonlar
   halinde — her P adımı ayrı test edilebilir fonksiyon) + `ingest/profile.py`
   (P9 raporu). Mevcut `ingest/loader.py` CSV okuma/doğrulama katmanı olarak
   kalır; canonicalize onun çıktısı üzerinde çalışır.
2. **CLI**: `inres build-data` (raw → processed + rapor; deterministik: aynı
   girdi aynı bayt çıktısı, kayıtlar id'ye göre sıralı yazılır). `inres index`
   artık raw değil `data/processed/` okur.
3. **Sıralama zorunlu değil ama doğal akış**: P1→P2 (filtreler) → P3 (merge,
   çünkü anahtarı normalized_name'e bağlı) → P4–P5 (kind_label + qualifier
   soyma) → P6 (zincir) → P7–P8 → P9 (rapor en son, tüm adımların önce/sonra
   sayaçlarını toplar). Dikkat: P5'teki qualifier soyma `normalized_name`'i
   değiştirir → P3 merge anahtarı **soyma ÖNCESİ** ada göre kurulur (bugünkü
   ölçümler o anahtarla yapıldı; soyma-sonrası anahtar İÖ ikizlerini ve
   tezli/tezsizi yanlışlıkla birleştirir).
4. **Testler önce yazılır** (v2'nin (YL)-bug dersi): her P adımı için bu
   belgedeki ölçülmüş vakalar birebir fikstür olur — Bilkent 305→150 devri,
   SBÜ 165'linin tek kayda inmesi, Gazi 11'lisinin BİRLEŞMEMESİ, id=118/356/239
   muafiyeti, (İÖ) ikizinin ayrı kalması, zincirli adın ilk-segment kırpımı.
5. **Kabul kriterleri** (`transform_report.json` üzerinden assert):
   - Çıktıda `(parent_id, normalized_name(raw), kind_label)` tekrarı = 0.
   - Her subunit `parent_id`'si çıktıdaki bir parent'a çözülüyor (yetim = 0).
   - Satır sayıları Bölüm 2'nin tablosuyla uyumlu (±0; sapma varsa dump
     değişmiştir, rapor açıklamalı).
   - `merged_ids` birleşimi = girdi aktif id kümesi (id kaybı yok).
6. **Downstream'e dokunan iki iş bu planla AYNI turda yapılmalı** (ikisi de
   reindex gerektirir, iki kez reindex etmeyelim): `unit_type`/`program_type`
   alanlarının ES mapping'ine eklenmesi ve embed metninin yeni şemadan
   (`hierarchy_context` dahil) üretilmesi.

---

## 5. Açık sorular (dosyaya karar yazılmadan kapanmayacak)

1. **(İÖ) sert birleştirme mi, yumuşak tercih mi?** Şu an: ayrı kayıt +
   decide'da İÖ'süz tercih kuralı. Alternatif: İÖ kaydını ikizinin
   `merged_ids`'ine katmak (o zaman İÖ ayrımı çıktıda kaybolur — downstream
   buna razı mı? Ürün kararı).
2. **Çıplak sorguda katman tercihi**: "gazi istatistik" 11 kayda düşer;
   qualifier yoksa Bölüm/ABD katmanı programlara tercih edilmeli mi? (Öneri:
   evet, unit_type'lı kayıt program kaydına tercih edilir — ama bu decide
   katmanı işi, bu belgenin değil. v3 karar-katmanı dosyasına taşınacak.)
3. **Muaf-inaktif üç üniversitenin** (118, 356, 239) `active=false` olma nedeni
   kaynakta sorulmalı — veri hatasıysa upstream'de düzelt, değilse anlamını
   öğren.
4. **ror_child karışımı** (hastane/şirket/üniversite) ileride kendi içinde
   sınıflanmalı mı? Şimdilik bayrakla erteleniyor.
5. **`%81 paylaşılan ad` bu pipeline'ın çözdüğü bir şey DEĞİL** — parent'sız
   "istatistik bölümü" sorgusu tanım gereği belirsiz kalır. Çözüm yeri:
   id-listesi çıktısı + parent-koşullu metrik + review/LLM-hakem triyajı.
   Buraya not düşüldü ki kimse bu planın onu çözmesini beklemesin.
