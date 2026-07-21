# v3 Başlangıç Rehberi — Temiz Başlangıç: ES + LLM Karar Katmanı

> Tarih: 2026-07-17. Amaç: `"gazi üniversitesi mühendislik fakültesi makine
> mühendisliği"` → parent: **GAZİ ÜNİVERSİTESİ**, subunit: **doğru bölüm kaydı**.
> Aday üretimi Elasticsearch'te, nihai karar bir **LLM katmanında**.
>
> Bu rehber sıfırdan yazılmıştır ama v2'nin 28 commit'lik deney tarihçesinin
> (EXPERIMENTS.md) ödenmiş derslerini tasarıma gömer — aynı hataları yeniden
> yaşamamak bu rehberin varlık sebebidir. v2 kodu referans olarak durur;
> nereden ne kopyalanacağı Bölüm 8'de.

---

## 0. Sistem sözleşmesi (önce çıktıyı sabitle)

**Girdi:** serbest metin kurum ifadesi (tek satır, ≤512 karakter).

**Çıktı (her sorgu için tek JSON):**

```json
{
  "query": "gazi üniversitesi mühendislik fakültesi makine mühendisliği",
  "parent":  { "id": "1042", "name": "GAZİ ÜNİVERSİTESİ", "decision": "auto_match", "confidence": 0.97 },
  "subunit": { "id": "88123", "merged_ids": [], "name": "MAKİNE MÜHENDİSLİĞİ BÖLÜMÜ",
               "decision": "auto_match", "confidence": 0.94 },
  "evidence": { "stage": "llm", "reason": "sorgu fakülte+bölüm belirtiyor; aday parent_id eşleşiyor" }
}
```

Baştan kabul edilen üç sözleşme kararı (v2'de sonradan, acıyla öğrenildi):

1. **`merged_ids` çıktı tipinin parçasıdır.** Veride 5.333 grup birebir
   ayırt-edilemez klon var (SBÜ altında 165× "ALGOLOJİ BİLİM DALI") — bunlar
   tek kayıt olarak döner, id listesi taşır. Tek-id zorlaması v2'de
   auto_match'i matematiksel imkânsıza çevirmişti.
2. **Karar etiketleri:** `auto_match` / `review` / `ambiguous` / `no_match`.
   `no_match` birinci sınıf vatandaş — gerçek verinin önemli bir dilimi kurum
   değil ("Emekli", "Serbest Diş Hekimi", e-posta, atıf parçası).
3. **Subunit doğruluğu parent-koşulludur.** Aktif subunit adlarının %81'i
   başka üniversitelerle paylaşılıyor; sorguda üniversite yoksa subunit tek
   başına tanım gereği `ambiguous`tur. Hedef metrik buna göre kurulur.

---

## 1. Veri gerçekleri — yeniden keşfetme, tasarıma göm

Hepsi ham CSV'de ölçülmüş, iki kez doğrulanmış (EXPERIMENTS.md +
FABLE_RETROSPEKTIF.md):

| Gerçek | Tasarım sonucu |
|---|---|
| Parent 106.331 / subunit 179.106 satır; aktif subunit 138.298 | `active=false` satırlar ingest'te atlanır (40.808'i — %99'u zincirli legacy çeviri, hepsi boş kind_label) |
| Subunit adlarının %98'i düz ("MAKİNE MÜHENDİSLİĞİ BÖLÜMÜ"), %2'si zincirli ("X ÜNİV, Y FAK, Z PR.") | İki tip tek şemaya eritilir: `unit_name` + `hierarchy_path` (Bölüm 2.2) |
| 5.333 klon grubu, 13.557 fazla satır — üyeler alias'larına kadar özdeş, ayırt edici alan YOK (4 sinyalle kanıtlandı) | Ingest'te birleştir + `merged_ids`. Ayırt etmeye ÇALIŞMA — o yol kapalı |
| %81 paylaşılan subunit adı ("bilgisayar teknolojileri bölümü" 404 kayıt/176 üniversite) | Parent-koşullu karar; LLM'e parent tutarlılığı kural olarak verilir |
| kind_label: 24 temiz değer (Anabilim Dalı 36K, Bölüm 21.4K, Fakülte 2.3K...) | Index'e keyword alan olarak girer; LLM bağlamına yazılır ("bölümü" diyen sorguya Doktora Programı önerme) |
| ror_child %10.8 (yabancı kurum/şirket karışımı) | `kind_label` ile filtrelenebilir; TR-üniversite akışında LLM'e etiketiyle gider |
| `iz`/`top_iz` boş (138K'da 4), ara hiyerarşi yok | Fakülte→bölüm ilişkisi VERİDE YOK; sorgudaki "mühendislik fakültesi" bilgisi ancak metin eşleşmesi/LLM muhakemesiyle kullanılır, FK beklenmez |
| Alias `locale` güvenilmez (39K "tr" etiketli İngilizce), `source="yok"` düşük kalite | Dil kararı içerik-kanıtından; `source="yok"` alias'lardan akronim üretilmez |
| Kısa akronimler çok anlamlı (KTU=4 gerçek kurum, IDA/ADA/IPM...) | Kısa-akronim sorguları için LLM'e açık "birden fazla meşru sahip varsa AMBIGUOUS" kuralı |
| Qualifier'lar subunit'te %25.3, parent'ta %1.0; tezli/tezsiz ayrımını embedding YAPAMAZ (v1+v2 kanıtlı) | Qualifier çıkarımı ingest'te + sorguda; tezli/tezsiz çelişkisi **kod tarafında** sert kural (LLM'e ek olarak — Bölüm 5.3) |
| Türkçe tuzaklar: İ/I ("TIP" ≠ "tip"), `\b\(yl\)\b` regex'i asla eşleşmez, NBSP/ZWSP/BOM, "Prof. Dr." hastane adları | normalize modülü v2'den AYNEN alınır — 236 testiyle birlikte (Bölüm 8) |

---

## 2. Mimari

```
                     INDEXLEME (offline)
CSV'ler → ingest (aktif filtre + klon-merge + qualifier/kind çıkarımı + kalite raporu)
        → embed metni (tüm alias + parent-adı enjeksiyonu)  [kanıtlı kazanım]
        → encoder (multilingual-e5-base)                    [Gemma test edildi, kazanç yok]
        → ES: TEK index "institutions_v1" + alias "institutions"
              (turkish analyzer + ascii + edge_ngram + dense_vector)
        → force-merge 1 segment                             [determinizm, gün-1]

                     SORGU ANI
girdi → normalize (casefold, kısaltma genişletme, qualifier çıkarımı)
      → ES hibrit arama ×2 (record_type=parent / =subunit filtresiyle)
           BM25+fuzzy+akronim  ∥  kNN     → RRF SADECE havuzlama
           her adaya HAM bm25 (havuz-max normalize) + cosine iliştirilir [gün-1]
      → DETERMİNİSTİK KAPI (Bölüm 4): kolay vakalar LLM'siz biter
      → LLM KARAR KATMANI (Bölüm 5): kalan her şey
      → doğrulayıcılar (halüsinasyon/qualifier/parent-tutarlılık) → çıktı JSON
```

### 2.1 Tek index, `record_type` alanı

v2 iki ayrı index kullandı ve bedelini ödedi: "fakültesi" parent index'inde
4 belgede geçtiği için sahte-yüksek IDF aldı, "ankara üniversitesi tıp
fakültesi" sorgusu Erciyes hastanesine gitti. **Tek korpus IDF'si + sorgu
anında `term: {record_type}` filtresi.** Parent sorgusunda subunit-jenerik
kelimeleri düşürme hilesine (v2 `strip_subunit_only_terms`) muhtemelen gerek
kalmaz — ama F2 kabul testine "ankara üniversitesi tıp fakültesi → ANKARA
ÜNİVERSİTESİ" regresyon sorgusu yine de konur.

### 2.2 Belge şeması

```
id              : keyword           # kanonik id (birleşen grubun en küçüğü)
merged_ids      : keyword[]         # klon-merge'de emilen id'ler (çoğunlukla boş)
record_type     : keyword           # parent | subunit
parent_id       : keyword           # subunit için FK
parent_name     : text              # denormalize — arama + LLM bağlamı için
unit_name       : text (turkish + ascii + edge_ngram alt alanları)
hierarchy_path  : text[]            # zincirli addan sökülen ara segmentler (varsa)
kind_label      : keyword           # 24 değer, index'e İLK GÜNDEN girer (v2'de hep ölü kaldı)
aliases         : nested { name, normalized, ascii, locale, source, is_acronym }
qualifiers      : { thesis, modality, language, degree, extra[] }   # ingest'te dolu
embedding       : dense_vector(768, cosine)
```

Ingest kuralları:

- **Zincirli ad** (virgüllü): son segment → `unit_name`; öndekiler →
  `hierarchy_path`; segment kendi parent adıyla eşleşiyorsa path'e girmez
  (çift-enjeksiyon biter); tam zincir alias olarak korunur.
- **Klon-merge:** aynı `(parent_id, normalize(unit_name), kind_label)` VE
  özdeş alias kümesi → tek kayıt, `merged_ids` dolu. Kalite raporuna
  önce/sonra satır sayısı.
- **Self-parent filtresi:** adı kendi parent'ıyla birebir aynı subunit atlanır
  (v2 Sorun 1B, 43 kayıt).
- **Akronim üretimi:** v2'nin üç kanıtlı kuralıyla — stopliste
  {REKTÖRLÜK, RECTORATE, MÜDÜRLÜK, DEKANLIK}, `source="yok"` dışlanır,
  virgül/slash listesi ancak TÜM parçalar akronim-şekilliyse bölünür
  ("METU, ODTÜ" evet; "RADYO, TELEVİZYON VE SİNEMA" hayır).
- **Embed metni:** `passage: {parent_name} - {hierarchy_path...} - {tüm alias'lar}`
  — tüm-alias + parent-enjeksiyonu v1'den beri kanıtlı, aynen korunur.

### 2.3 Determinizm gün-1 kuralı

Indexleme pipeline'ının SON adımı: `_forcemerge?max_num_segments=1` + arama
gövdesinde `sort: [_score desc, id asc]`. v2 bunu geç öğrendi ve ondan önceki
~10 ayar turu kayan zeminde koşuldu ("City of Antwerp" flip-flop'u, sahte
0.9903 tabanı). Ayrıca CI'ya determinizm testi: aynı sorgu ×5 → özdeş sonuç.

---

## 3. LLM'in varlığının sadeleştirdiği şey: ağırlık ormanı YOK

v2'nin en çok emek yiyen katmanı 8-sinyallik konveks ağırlık kombinasyonu +
eşik kalibrasyonuydu (5+ tur ağırlık kaydırma; öğrenilmiş ağırlık iki kez
denendi, ikisi de held-out'ta geri alındı). **v3'te bu katman kurulmaz.**
Sinyaller yine hesaplanır ama iki mütevazı işe yarar:

1. **Deterministik kapının** basit kuralları (Bölüm 4),
2. **LLM bağlamına kanıt** olarak yazılmak (aday başına 3-4 sayı).

Skorların tek bir "kalibre güven puanına" indirgenmesi zorunluluğu —
v2'deki eşik-ağırlık bağlaşımının, kümelenme ucurumlarının, kalibrasyonun
kaynağı — LLM kararıyla birlikte ortadan kalkar.

Hesaplanan sinyaller (hepsi v2'den hazır): `bm25_norm` (havuz-max'e göre),
`knn_cosine`, `token_set_ratio` (aksan-toleranslı max), `partial_ratio`
tabanlı **lexical_floor**, `qualifier_conflict` (bool), `parent_match` (bool).

---

## 4. Deterministik kapı — LLM'e gitmeyenler

Amaç: maliyet ve gecikme. 438K satırlık batch hedefi LLM'i her satıra
çağırmayı kaldırmaz; kapının hedefi trafiğin **%40-60'ını LLM'siz** bitirmek.
Üç kural, üçü de v2'de kanıtlı mekanizmalar:

| Kural | Koşul | Karar |
|---|---|---|
| **Çöp kapısı** | `lexical_floor < 0.55` (en iyi adayla bile zayıf dizge örtüşmesi) | doğrudan `no_match` — v2 floor-kapısı: gerçek veride "Emekli"/adres/e-posta sınıfını güvenle eledi |
| **Açık-ara kapısı** | top-1 `token_set_ratio ≥ 0.95` VE `bm25_norm = 1.0` VE marj (top1−top2, merge sonrası) ≥ 0.15 VE qualifier çelişkisi yok VE sorgu tek-token-kısa-akronim DEĞİL | doğrudan `auto_match` — "Süleyman Demirel Üniversitesi" tipi net vakalar |
| **Boş havuz** | ES iki havuzda da 0 aday | `no_match` |

Geri kalan her şey (gri bant 0.55-0.95, kardeş-birim seçimi, çok-dilli
eşleşme, kısa akronimler) → LLM. Eşikler F4'te gerçek etiketli set üzerinde
bir kez ayarlanır — **sentetik set üzerinde tur tur ayar yok** (v2'nin K5
dersi).

---

## 5. LLM karar katmanı

### 5.1 Girdi (yapılandırılmış, kompakt)

Sorgu + iki aday listesi (parent top-5, subunit top-10 — subunit'te kardeşler
yarıştığı için daha geniş). Aday başına:

```
{id, name, parent_name, kind_label, qualifiers, matched_alias,
 bm25_norm, knn_cosine, token_set_ratio, merged_count}
```

### 5.2 İstenen çıktı (kısıtlı JSON — serbest metin değil)

```json
{ "parent":  {"verdict": "MATCH|NONE|AMBIGUOUS", "id": "...", "confidence": 0.0},
  "subunit": {"verdict": "MATCH|NONE|AMBIGUOUS|NOT_APPLICABLE", "id": "...", "confidence": 0.0},
  "query_type": "INSTITUTION|NOT_INSTITUTION|UNCLEAR",
  "reason": "tek cümle" }
```

### 5.3 Prompt'a gömülecek kurallar (her biri v2'de ödenmiş bir dersin karşılığı)

1. "id'yi YALNIZ verilen aday listesinden seç" — ve **kod tarafında doğrula**
   (listede olmayan id → `review`'a düşür; halüsinasyon sigortası).
2. "Sorgu tezli/tezsiz/İÖ/derece belirtiyorsa çelişen adayı SEÇME" — ve
   **kod tarafında ikinci kez doğrula** (`qualifier_conflict` bool'u;
   LLM'e güven ama sert kuralı koddan kaldırma — v2'nin kurucu ilkesi).
3. "Seçtiğin subunit'in `parent_name`'i, seçtiğin parent ile aynı olmalı;
   değilse subunit için AMBIGUOUS de" — parent-tutarlılık, kodda da kontrol.
4. "Sorgu 2-4 harfli tek bir kısaltmaysa ve listede bu kısaltmayı taşıyan
   birden fazla FARKLI kurum varsa AMBIGUOUS de" — IDA/ADA/KTU dersi;
   lineer sistemin yapısal olarak çözemediği sınıf, LLM'in de tahmin ETMEMESİ
   gereken sınıf.
5. "Girdi bir kurum adı değilse (meslek unvanı, adres, e-posta, dergi/atıf)
   NOT_INSTITUTION de" — gerçek verinin gri bandı (0.60-0.90 skorla review'a
   sızan "Serbest Diş Hekimi" sınıfı); LLM'in en güçlü olduğu iş.
6. "Sorgu yalnız birim adı içeriyorsa (üniversite yok) parent için NONE,
   subunit için AMBIGUOUS de" — %81 paylaşılan ad gerçeği.
7. Çeviri eşdeğerliği serbest: "Ticaret Üniversitesi" ↔ "Commerce University"
   eşleşmesini metin benzerliği düşük olsa da tanıyabilirsin — v2'nin
   çözemediği Istanbul Ticaret/Commerce sınıfı.

### 5.4 Karar eşlemesi

- `MATCH` + confidence ≥ 0.9 + doğrulayıcılar temiz → `auto_match`
- `MATCH` + daha düşük güven → `review` (top-1 önerisiyle)
- `AMBIGUOUS` → `ambiguous`; `NOT_INSTITUTION`/`NONE` → `no_match`
- Doğrulayıcı ihlali (2/3. kural) → her zaman `review`'a indir, asla yükseltme.

### 5.5 Model ve maliyet

- **Varsayılan: küçük/hızlı model (Haiku sınıfı).** Görev kapalı-seçenekli,
  bağlam kısa (~1-2K token). 1806-satır gerçek örneklemde ölç: $/1000 satır,
  s/satır.
- **Önbellek:** normalize edilmiş sorgu metni anahtar — gerçek affiliasyon
  verisinde tekrar oranı yüksek (v2 batch memoization dersi). Cache +
  deterministik kapı birlikte, LLM çağrısını benzersiz-gri-sorgu sayısına
  indirir.
- Batch modda paralel/asenkron çağrı; `--resume` + satır-düzeyi hata
  toleransı (v2 batch iskeleti hazır).
- Opsiyonel kademe: Haiku `UNCERTAIN`/düşük-güven derse Sonnet'e yükselt —
  ancak F4 ölçümü gerektirirse.

---

## 6. Değerlendirme — gerçek set birincil, sentetik ikincil (v2'nin tersi)

v2'nin en pahalı metodolojik hatası: tüm kararlar sentetik gold set üzerinde
alındı, gerçek transfer sonradan şok yarattı (sentetik auto %18 ↔ gerçek %5).

1. **F0'da 400-500 gerçek satır etiketlenir** (`data/inbox` örnekleminden;
   LLM ön-etiket + insan onayı — etiketleme aynı zamanda prompt'un ilk
   provasıdır). Etiketler: parent_id / subunit_id-veya-grup / KURUM_DEGIL /
   BELIRSIZ. **Bu set eğitime/prompt-ayarına DEĞİL yalnız kabule kullanılır;**
   prompt ayarı için ayrı 100-150 satırlık ikinci bir dilim ayrılır
   (ayar/kabul ayrımı = v2'nin seed42/seed7 kuralının gerçek-veri karşılığı).
2. **~50 sorguluk sabit CI fikstürü** (ES + mock-LLM ile saniyeler):
   bilinen vakalar — "gazi üniversitesi mühendislik fakültesi makine
   mühendisliği", "ankara üniversitesi tıp fakültesi" (IDF), "ODTÜ" (akronim),
   "KTU" (çok-anlamlı → ambiguous), "Emekli" (no_match), "EBELİK (YL) (TEZLİ)"
   (qualifier), SBÜ Algoloji (merged_ids), "City of Antwerp" (determinizm).
3. Sentetik gold+noise (v2 `eval/` aynen) yalnız regresyon dumanı olarak.

**Kabul metrikleri (gerçek sette):**

| Metrik | Hedef |
|---|---|
| auto_match kesinliği | ≥ %98 (bu sistemin kritik kısıtı — v2 ile aynı ilke) |
| Parent doğruluğu (kurum-olan satırlarda) | ≥ %90 (v2 tavanı ~%90'dı; LLM çeviri/gri vakalarla üstüne çıkmalı) |
| Parent-koşullu subunit doğruluğu | raporlanır, taban v2 ile kıyaslanır |
| KURUM_DEGIL yakalama | ≥ %80 (v2'de floor-kapısıyla kısmi) |
| LLM'siz çözülen oran + $/1000 satır | raporlanır, bütçeyle kıyaslanır |

---

## 7. İnşa sırası

| Faz | İçerik | Kabul kanıtı |
|---|---|---|
| **F0** (2-3 gün) | Veri profili scripti (klon grupları, ad-paylaşımı, alan doluluk — quality raporunun kalıcı parçası) + 400-500 gerçek etiket + CI fikstürü | Etiketli set + profil raporu repoda; `pytest` iskeleti <30 sn |
| **F1** (2-3 gün) | Ingest: aktif filtre, klon-merge, self-parent, zincirli→unit_name/path, qualifier+kind çıkarımı, akronim kuralları. **Her kural testiyle doğar** | Merge önce/sonra sayıları raporda (~5.3K grup); unit testler yeşil |
| **F2** (2-3 gün) | ES: tek index mapping, indexer + force-merge, hibrit sorgu (ham skorlar iliştirilmiş), determinizm testi. **Önce lexical-only** — v2 kanıtı: doğru cevap %87 vakada zaten havuzda, darboğaz karar katmanıydı | "ankara tıp fakültesi" + KTÜ regresyon sorguları; determinizm ×5 |
| **F3** (1-2 gün) | Embedding + kNN eklenir (e5-base, v2 cache formatı); sinyal hesaplama + deterministik kapı | Kapının LLM'siz çözdüğü oran gerçek örneklemde ölçülür; çöp kapısı 35 meslek-unvanı fikstürünü geçer |
| **F4** (3-4 gün) | LLM katmanı: prompt + kısıtlı JSON + 3 doğrulayıcı + cache; ayar dilimiyle prompt iterasyonu; kabul dilimiyle TEK ölçüm | Bölüm 6 tablosundaki hedefler; $/1000 raporu |
| **F5** (2 gün) | Batch CLI (resume/memoization/CSV-injection koruması — v2'den taşınır) + çıktı JSON/CSV + EXPERIMENTS.md v3 günlüğü açılır | 1806-satır uçtan uca koşu, 0 hata; karar dağılımı v2 tabanıyla yan yana |

Toplam: **~2,5-3 hafta.** Her fazda EXPERIMENTS disiplini aynen: hipotez →
ölçüm → karar; davranış değişikliği = önce/sonra eval.

---

## 8. v2'den ne taşınır, ne taşınmaz

**Aynen taşı (kanıtlı + test-kilitli):**
- `normalize/` tamamı — turkish_lower, aksan-duyarsız qualifier eşleşmesi
  (Yaklaşım B), veri-doğrulanmış kısaltma sözlüğü (PR.→PROGRAMI 28.5K kayıt),
  parantez-bağımlı (dr)/(yl)/(iö) kalıpları, görünmez-karakter temizliği
  — ve bunların ~60 unit testi.
- `elastic/mappings.py` analyzer konfigürasyonu (turkish + ascii + edge_ngram)
  — mapping'in kendisi tek-index şemasına uyarlanır.
- `embedding/text_builder` mantığı + encoder + cache.
- Akronim kuralları (stopliste, source-filtresi, liste-şekil kontrolü) ve
  testleri.
- `cli/batch.py` dayanıklılık iskeleti (satır try/except, `--resume` + flush,
  memoizasyon, CSV-injection öneki, 512 kırpma).
- `eval/noise.py` + bootstrap CI kodu.
- Force-merge + id-sort determinizm çözümü.

**Taşıma (bilinçli olarak geride kalır):**
- 8-sinyal konveks ağırlık kombinasyonu, `weights_parent/subunit`, ağırlık
  öğrenme altyapısı — LLM katmanı bu sorunu ortadan kaldırıyor.
- `decide/policy.py` eşik ormanı + `calibrate_score` — yerine 3 kurallı
  deterministik kapı + LLM eşlemesi.
- İki-index mimarisi ve `strip_subunit_only_terms` yaması — tek index kökten
  çözüyor (F2 regresyon sorgusuyla doğrulanır).
- Sentetik-set-birincil eval kültürü.

---

## 9. Örnek akış — hedef sorgu üzerinden

`"gazi üniversitesi mühendislik fakültesi makine mühendisliği"`

1. **normalize:** küçük harf, kısaltma yok, qualifier yok →
   `"gazi üniversitesi mühendislik fakültesi makine mühendisliği"`.
2. **ES parent araması** (record_type=parent, tek-korpus IDF): top-1
   GAZİ ÜNİVERSİTESİ (bm25_norm=1.0, token_set≈0.95 — sorgunun fazla
   token'ları set-oranını biraz düşürür).
3. **ES subunit araması:** havuzda GAZİ'nin "MAKİNE MÜHENDİSLİĞİ BÖLÜMÜ",
   "MAKİNE MÜHENDİSLİĞİ PR.", "MAKİNE MÜHENDİSLİĞİ (YL)..." kardeşleri +
   diğer üniversitelerin aynı adlı bölümleri.
4. **Deterministik kapı:** parent açık-ara kuralını geçebilir → parent
   `auto_match` LLM'siz. Subunit gri: kardeşler yakın skorlu → LLM'e.
5. **LLM:** sorguda "fakültesi ... mühendisliği" var, derece/program eki yok;
   kural 3 gereği parent_name=GAZİ olan adaylardan, kind_label=Bölüm olanı
   seçer ("PR."/(YL) varyantları değil) → `MATCH`, confidence 0.94.
6. **Doğrulayıcılar:** id listede ✓, qualifier çelişkisi yok ✓,
   parent tutarlı ✓ → subunit `auto_match`.
7. **Çıktı:** Bölüm 0'daki JSON.

---

## 10. İlk hafta yapılacaklar listesi (somut)

```bash
# 1. Yeni çalışma alanı (v2 repo'su referans olarak yanında kalır)
mkdir institution_resolver_v3 && cd institution_resolver_v3 && git init
# v2'den taşınacak modüller (Bölüm 8 listesi) testleriyle kopyalanır

# 2. F0 — profil + etiket
python scripts/profile_corpus.py      # klon grupları, ad paylaşımı, alan doluluğu
inres-v3 label-set --input sample_500.csv   # LLM ön-etiket + insan onayı

# 3. F1-F2 — ingest + ES
docker compose up -d                  # v2'nin compose'u aynen
inres-v3 ingest && inres-v3 index     # merge raporu + force-merge dahil
pytest tests/unit -q                  # her kural testiyle doğdu mu?

# 4. Smoke
inres-v3 match "gazi üniversitesi mühendislik fakültesi makine mühendisliği"
```

**İlk hafta sonunda elde olması gerekenler:** etiketli gerçek set, klonsuz
tek index, çalışan hibrit arama, CI fikstürü. LLM katmanı (F4) ancak bunların
üstüne oturur — önce zemin, sonra hakem.
