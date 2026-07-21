# DURUM ve PLAN — Institution Resolver v3

> Bu dosya devamlılık içindir: oturum kapanıp açılsa da (veya yeni bir Claude
> oturumu) buradan tam bağlamı alır. Güncel tut. Son güncelleme: 2026-07-21.

## Amaç

Serbest metin kurum ifadesini (`"gazi üniversitesi istatistik bölümü"`) kanonik
**parent_id + subunit_id**'ye çözmek. Aday üretimi **Elasticsearch**'te, nihai
karar bir **LLM hakem katmanında**. Eşleşme bulunduktan sonra kaydın JSON'undaki
diğer bilgiler (ülke, ror linki, alias'lar) isteğe bağlı dönebilir.

## Mimari (değişmez)

```
Girdi → NORMALIZE → ELASTICSEARCH (aday havuzu: parent + subunit)
     → RETRIEVE (sinyaller) → GATE (deterministik, kolaylar) → JUDGE (LLM)
     → DECIDE (auto_match / review / ambiguous / no_match) → JSON çıktı
```

- **ES'in işi:** aday bulmak. **LLM'in işi:** adaylar arasından seçmek.
- Katmanlar ayrı paket: `retrieve/ gate/ judge/ decide/` — birbirine sızmaz.
- **v2'den import YOK** — kanıtlı parçalar kopyalanır (normalize gibi), test edilir.

## Alınan kararlar (bu oturumda, kullanıcı onaylı)

| Konu | Karar |
|---|---|
| Veri kaynağı | Ham CSV'den yeniden üret (B seçeneği); kayıp `canonicalize.py`'nin yerine test-kilitli pipeline |
| Çıktı formatı | **JSONL** (CSV-içi-JSON acı veriyordu) |
| Aktif filtre | `active=false` subunit'ler atılır (179K→138K) |
| Klon-merge | **Alias-farkındalıklı**: parent+ad+kind+alias-değer-kümesi aynıysa birleş (125.108). Bankacılık-tipi 193 kayıt ayrı kalır (over-merge geri dönülemez) |
| kind_label (P4) | 24 değer → `unit_type`/`program_type` + bayraklar |
| P5 (qualifier soyma) | **ATLANDI** — bilgi zaten P4'te |
| P6 (zincirli ad) | **ATLANDI** — Türkçe zincir-çöp formatı aktif veride yok (P1 süpürdü); kalan virgüller yabancı kurum adları |
| Yabancı kurumlar | **Tut + işaretle** (country + is_ror_child), sorgu anında filtrele — geri dönülebilir |
| Kurum akronimi (GÜ, ODTÜ) | **Üretme** (karışıyor); veride hazır olan alias'lar yine gelir |
| Kısaltma genişletme (üni.→üniversitesi) | **Kullan** (`abbreviations.py`) |
| Normalize | Türkçe fold **kalır** (İ tuzağı + aksan ü→u); yabancı é/ñ önemsiz |
| Embedding metni | Agresif normalize DEĞİL — doğal metin (case+aksan), folding'i ES/model yapar. Agresif normalize sadece iç anahtar (merge/dedup/keyword-eşleşme) |
| İndeks | **TEK index** + `record_type` filtresi (v2 iki-index IDF zehirlenmesini çözer) |
| Retrieval | **Lexical-first** (BM25+fuzzy); kNN/embedding F3'te |
| **Açık kararlar** (F4'e kadar ertelendi) | (a) LLM auto'ya terfi edebilir mi? — önerim: hayır, LLM düşürür, deterministik kanıt yükseltir. (b) İÖ sert-merge mi yumuşak-tercih mi. (c) Batch ölçeği/bütçe |

## Durum — build order

| Faz | İçerik | Durum |
|---|---|---|
| **F0** | Kanonik veri (JSONL) + normalize entegrasyonu | ✅ BİTTİ |
| **F1** | ES tek-index + lexical arama + indexer | ✅ BİTTİ |
| **F3 (embedding)** | e5-base embed + hibrit arama (BM25+kNN, RRF) — index'te 231.291 vektör | ✅ BİTTİ |
| **F2** | **Gerçek sette recall@k ölç** (darboğaz retrieval mı karar mı?) + parent-first cascade'i retrieve katmanına kur | ⏭️ SIRADA (etiketli set ertelendi) |
| F3 (kalan) | sinyal hesabı (retrieve/) + deterministik gate | — |
| F4 | LLM hakem katmanı (tek çağrı parse+judge) + doğrulayıcılar + gerçek sette ölç | — |
| F5 | Batch (resume/memoization) + çıktı + EXPERIMENTS günlüğü | — |

**F2 revizyon notu (Ayrım 0):** karar katmanını optimize etmeden ÖNCE gerçek sette
recall ölç — darboğaz retrieval ise LLM'i düzeltmenin faydası yok.

## SIRADAKI İŞLER (öncelik sırası, detaylı yol haritası)

### 1. `retrieve/` katmanı — query decomposition + parent-first cascade + sinyaller  [ETİKET/API GEREKTİRMEZ — İLK YAP]

**Neden (canlı denemelerden kanıtlanmış çıkarım):** İKİ yapısal sorun var:
- **Parent kirlenmesi:** sorgu, kurum adının yanında gürültü (konum bilgisi, birim/fakülte kelimeleri)
  taşıyınca parent araması sapıyor ve gürültüyle örtüşen yanlış kurumları öne çıkarıyor; parent'ı
  yalnızca **çıkarılan kurum kısmıyla** aramak bu sapmayı gideriyor.
- **Subunit sıralaması:** parent çözülüp subunit `parent_id` ile filtrelenince, üniversite token'ı
  ayırt ediciliğini kaybediyor ve asıl birim adı doğru kaydı üste taşıyor.

**Yapılacaklar:**
- `retrieve/decompose.py`: sorguyu **kurum işaretçisiyle** böl (`üniversitesi/university/enstitüsü/
  institute/hastanesi/koleji/yüksekokulu`...; kısaltma genişletme "üni."→"üniversitesi" zaten var).
  Kurum kısmı = başından işaretçiye kadar (dahil); birim kısmı = sonrası. **İşaretçi yoksa** tam sorgu (fallback).
- `retrieve/resolve.py`:
  - parent araması = **kurum kısmı** (gürültüsüz → doğru kurum öne çıkar)
  - **parent-first cascade:** en güçlü parent'a göre subunit'i `parent_id` ile filtrele.
    **Recall-güvenli:** filtreli + filtresiz sonuçları birleştir (parent yanlışsa doğru subunit kaybolmasın); eşik tahmini YOK.
  - **sinyaller** (aday başına): `bm25_norm`, `cosine`, `token_set_ratio` (rapidfuzz), `qualifier_conflict`
- `match` komutu `resolve()` kullanacak şekilde güncellenir. Her adım kendi testiyle.

### 2. Sinyal katmanı tamamlama (F3 kalan)
Ham BM25 + cosine değerlerini **ayrı** çıkar (şu an RRF sıraya eziyor); gate + LLM'e kanıt olarak.

### 3. Deterministik gate (F3 kalan)
Çok net → auto adayı, çok çöp (lexical floor düşük) → no_match. **Eşikler F4'ten SONRA, gerçek sette ayarlanır** (körlemesine değil).

### 4. F2 — recall ölçümü  [ETİKET GEREKTİRİR — ertelendi]
Gerçek etiketli set (~150 pilot → gerekirse 400; LLM ön-etiket + insan onayı). v2 `real_labeled.csv` HATALI, kullanma.
recall@50 ölç: doğru cevap havuzda mı? Yüksek → karar sorunu (F4'e geç); düşük → retrieval'ı düzelt.

### 5. F4 — LLM hakem  [ANTHROPIC API GEREKTİRİR]
Adaylar + sinyaller → LLM doğru olanı seçer → `auto_match/review/ambiguous/no_match` + JSON.
Yetki asimetrisi (LLM düşürür, deterministik kanıt yükseltir) — karar bekliyor.

### 6. F5 — batch (resume/memoization) + çıktı + EXPERIMENTS günlüğü

### Açık kararlar (henüz verilmedi)
- LLM auto'ya terfi edebilir mi (yetki asimetrisi)?
- (İÖ) ikizleri: sert-merge mi yumuşak-tercih mi?
- Batch ölçeği/bütçe?
- Markersız sorgu decomposition ("hacettepe tıp fakültesi" — "üniversitesi" yok) nasıl?

---

## Neyi kanıtladık (bu oturum, canlı — çıkarımlar)

- Uçtan uca çalışıyor: net kurum-adlı sorguda parent doğru top-1, büyük marj.
- **Hibrit (BM25+embedding), lexical'e göre subunit eşleşmesini iyileştiriyor**
  (doğru birim, sadece-kelime sıralamasında geride kalırken anlam eşleşmesiyle öne çıkıyor).
- **Birleşik-sorgu kirlenmesi gerçek:** sorgu hem kurum hem birim/konum taşıyınca
  her iki havuz da sapıyor → çözüm decomposition + parent-first cascade (bkz. Sıradaki İşler 1).

## Nasıl çalıştırılır

```bash
# ES ayağa kaldır
cd docker && docker compose up -d && cd ..

# (kurulmadıysa PYTHONPATH ile; ya da: pip install -e ".[dev]")
export PYTHONPATH=src
alias inres3="python3 -m institution_resolver_v3.cli.main"

# veri üret (ham v2'de: ../institution_resolver_v2/data/raw)
inres3 build-data --raw-dir /Users/mscn/Desktop/institution_resolver_v2/data/raw
inres3 setup-es          # index + analyzer
inres3 index             # 231K kaydı yükle + force-merge
inres3 match "gazi üniversitesi istatistik bölümü"

# testler
python3 -m pytest tests/unit -q     # 89 test
```

## Kritik gerçekler (ham veri, ölçüldü)

- **Parent ve subunit id uzayları ÖRTÜŞÜYOR (55.431 ortak id)** — ES `_id` = `record_type:id`
  olmalı (ham id verilirse kayıtlar birbirini ezer). Gerçek id `_source.id`'de.
- **Embedding cache:** `data/processed/embeddings.npz` (679MB, 231.291×768). `index --embeddings`
  ids eşleşince encode'u atlar (23 dk'lık encode tekrarlanmaz). Encode MPS'te ~22 dk.
- Parent 106.331 (çoğu **küresel/ROR**, yabancı de var); subunit 179.106 → aktif 138.298.
- Merge sonrası: parent 106.183 (147 düş, Bilkent 305→150, 3 muaf), subunit 125.108.
- 24 kind_label değeri. En büyük klon grubu: SBÜ ~174× özdeş.
- Ham CSV: `../institution_resolver_v2/data/raw/` (161MB+217MB). JSONL çıktı gitignore'da.

## Kritik dosyalar

- `ingest/canonicalize.py` — P1-P4 saf fonksiyonlar (+ orchestrator `run_pipeline`)
- `ingest/build.py` + `cli` `build-data` — JSONL üretimi
- `normalize/query_pipeline.py` — normalize/expand (v2'den, `text_eski.py` eski deneme)
- `elastic/mappings.py` `document.py` `search.py` — ES katmanı
- `docs/V3_BASLANGIC_REHBERI.md` `V3_VERI_PLANI.md` — orijinal tasarım (ilham, şartname değil)

## Çalışma tarzı (önemli)

Plan dosyaları **ilham/girdi**, körü körüne uygulanacak şartname değil. Her önemli
kararı önce **tartış**, ham veriden **doğrula**, kullanıcı onayını al, sonra kod yaz.
Her kural kendi testiyle doğar.
