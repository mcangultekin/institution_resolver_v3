# DURUM ve PLAN — Institution Resolver v3

> Bu dosya devamlılık içindir: oturum kapanıp açılsa da (veya yeni bir Claude
> oturumu) buradan tam bağlamı alır. Güncel tut. Son güncelleme: 2026-07-30.

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
| **Parent aramasında kanonik/alias ayrımı** (2026-07-30) | **AYRIM YOK.** Bütün yazımlar (kanonik ad + her alias) tek ortak havuzda, her biri ayrı nested belge (`alias_variants`, `score_mode: max`). `name` ve birleşik `aliases_text` parent aramasından **çıkarıldı** — ikisi ayrı kanal olarak dururken kanonik ad her ikisini birden ateşleyip skor topluyordu, yani yapısal ayrıcalığı vardı. Ölçüm (200 kurum, canlı): alias ile top1 %47→%84.5, top10 %70.5→%99.5, havuz dışı %11→%0.5; kanonik ad %98.5→%100; aradaki uçurum 51.5→15.5 puan. **Subunit kapsam dışı** (`aliases_text` ile aranmaya devam eder). Ayrıntı ve ara varyantların ölçümleri: `search.py` `_alias_variants_clause` docstring'i |
| **Gate: parent'ta çoklu exact** (2026-07-30) | Parent havuzunda **birden fazla** güçlü exact varsa `auto_match` **verilmez** (`ambiguous`, reason `coklu_exact_herhangi`) — span farkına bakılmaz. Subunit'te eski kural (yalnız eşit-uzun rakip engeller) korunur. Ölçülen bedel (benchmark ilk 150 sorgu): 5 karar (%3.3) auto→ambiguous, hakeme giden sorgu +%2.0 (3 sorgu; 2'si zaten gidiyordu), 1 subunit kararı `_enforce_coherence` üzerinden review'e çekildi. Bu kural **hata önlemiyor**, "şüpheli auto yerine belirsizlik" risk tercihini uyguluyor — 5 vakada bugünkü seçim doğru görünüyordu (jenerik alt-parça rakipleri: `İSTANBUL ÜNİVERSİTESİ-CERRAHPAŞA` vs `İSTANBUL ÜNİVERSİTESİ`) |
| **Gate: parent auto_match değilse subunit kimlik önermez** (2026-07-30) | `_enforce_coherence` genişletildi: subunit `matched_id` taşıyabilmesi *yalnızca* parent `auto_match` VE seçilen subunit gerçekten o parent'ın altındaysa geçerli — artık sadece `auto_match→review` düşüşünde değil, subunit'in kendi `review`/`ambiguous` kararında da id `None`'a çekiliyor (verdict aynen korunur, sadece id atılır). Gerekçe: bu katalogda subunit kaydının gerçek kimliği (parent, ad) çiftidir — aynı ad onlarca farklı parent altında bağımsız gerçek kayıt olarak tekrarlanabiliyor (`bilgisayar mühendisliği bölümü` ×190). Parent bilinmeden verilen id, kaç aday arasından seçilirse seçilsin bir tahmindir. Kaybedilen fayda yok: subunit'in parent'ı "doğrulaması" (promosyon) zaten hiçbir katmanda (`decide/` dahil) kullanılmıyordu |
| **Judge: parent/subunit tutarsızlığı reddedilir** (2026-07-30) | Gate'teki aynı ilkenin hakem tarafı: hakem parent olarak X, subunit olarak GERÇEKTE başka bir parent'a (Y) ait bir kayıt seçerse (`sub_view.parent_id != result.parent.matched_id`), bu halüsinasyonla aynı sınıf sayılır — `JudgeValidationError` fırlatılır, sessizce geçilmez. `CandidateView`'a `parent_id` eklendi (önceden sadece `parent_name` vardı, karşılaştırma için id gerekiyordu) |
| **Açık kararlar** (F4'e kadar ertelendi) | (a) LLM auto'ya terfi edebilir mi? — önerim: hayır, LLM düşürür, deterministik kanıt yükseltir. (b) İÖ sert-merge mi yumuşak-tercih mi. (c) Batch ölçeği/bütçe |

## Durum — build order

| Faz | İçerik | Durum |
|---|---|---|
| **F0** | Kanonik veri (JSONL) + normalize entegrasyonu | ✅ BİTTİ |
| **F1** | ES tek-index + lexical arama + indexer | ✅ BİTTİ |
| **F3 (embedding)** | e5-base embed + hibrit arama (BM25+kNN, RRF) — index'te 231.291 vektör | ✅ BİTTİ |
| **retrieve/ katmanı** | `decompose.py` (ES-destekli sınır tespiti) + `resolve.py` (parent-first cascade + sinyaller) | ✅ BİTTİ (bkz. aşağıda) |
| **retrieve/ 1b** | Çoklu-hipotez + alias-farkındalıklı decompose + çoklu-parent cascade | ✅ BİTTİ (2026-07-23) |
| **F2** | Gerçek sette recall@k ölç | ❌ İPTAL (kullanıcı kararı — bkz. Sıradaki İşler 3) |
| F3 (kalan) | deterministik gate | — |
| **F4** | LLM hakem katmanı (`judge/` paketi: client+prompt+schema+candidates+doğrulayıcılar) — **Gemma 4 E2B, Ollama (yerel)** | ✅ BİTTİ (bkz. aşağıda) |
| F5 | Batch (resume/memoization) + çıktı + EXPERIMENTS günlüğü | — |

**F2 revizyon notu (Ayrım 0):** karar katmanını optimize etmeden ÖNCE gerçek sette
recall ölç — darboğaz retrieval ise LLM'i düzeltmenin faydası yok.

## SIRADAKI İŞLER (öncelik sırası, detaylı yol haritası)

### 1. `retrieve/` katmanı — query decomposition + parent-first cascade + sinyaller  ✅ BİTTİ

**İlk plan (marker/regex-tabanlı bölme) kullanıcı tarafından reddedildi** ("ilkel ve hatalara
gebe" — haklı çıktı, gerçek veriyle doğrulandı): `üniversitesi/university/enstitüsü/institute/...`
gibi sabit bir işaretçi listesiyle sorguyu bölmek iki gerçek veri deseninde kırılıyordu:
- İngilizce **"X of Y" ters-örüntüsü** ("University of Oxford" — işaretçi kurumun adını
  BAŞLATIYOR, bitirmiyor). Korpusta ~8.566/106.183 parent (%8) bu örüntüde.
- Türkçe **bileşik kurum adı** ("Eskişehir Osmangazi Üniversitesi Tıp Fakültesi Hastanesi" —
  zincirleme birden fazla işaretçi içeren TEK bir kurumun kendi adı, üniversiteye bağlı ama
  AYRI bir parent kaydı). 15 parent kaydında doğrulandı.

**Uygulanan çözüm — kural yazmak yerine korpusa sorma (ES-destekli sınır tespiti):**
`retrieve/decompose.py` sorgunun her olası kesim noktasını dener, her aday parça için ES'te
(BM25) en yakın parent'ı bulur, `rapidfuzz.fuzz.ratio` (uzunluk-duyarlı düz oran —
`token_set_ratio` DEĞİL, o fazla/eksik kelimeye tolerans gösterdiği için sınırı ayırt edemiyordu)
ile "bu parça gerçek bir kurum adına ne kadar tam örtüşüyor" diye ölçer; en yüksek skoru veren
kesim noktası kurum sınırı sayılır (eşitlikte daha uzun parça tercih edilir — bileşik ad durumunu
doğru çözer). Eşik YOK; düşük güvenli bölme bile zarar vermez çünkü cascade her zaman filtresiz
aramayı da tutar (aşağıda). **Mimari sonuç:** `decompose()` artık saf/ES-bağımsız değil (ama
`search_fn` enjekte edilebilir, testler gerçek ES gerektirmez). Doğrulama: `tests/unit/test_decompose.py`
(6 test) + canlı ES'te manuel doğrulama (Gazi/Ankara/Eskişehir/Oxford/gürültülü-sorgu/sadece-birim
senaryoları hepsi doğru ayrıştı).

`retrieve/resolve.py`:
- parent araması = `decomposed.institution_part`
- **parent-first cascade:** en güçlü parent'ın `parent_id`'siyle subunit'i filtrele; **recall-güvenli**
  birleşim (`_merge_filtered_first`): filtreli sonuçlar önce (`passed_parent_filter=True`), filtresizde
  olup filtrelide olmayanlar sona eklenir (parent yanlışsa doğru subunit kaybolmaz, sadece geriye düşer).
- **sinyaller** (aday başına, `ScoredCandidate`): `bm25_norm` (ham BM25, sorgu-içi max'a bölünerek
  [0,1]), `cosine` (ES kNN skorundan `2*es_score-1` ile geri çıkarılır — `similarity=cosine` mapping),
  `token_set_ratio` (rapidfuzz), `qualifier_conflict` (var olan `normalize.qualifiers` fonksiyonu).
  BM25+kNN artık RRF'den ÖNCE ayrı ayrı da tutuluyor (RRF sadece havuzlama/sıralama için) — eski
  "F3 kalan: ham skorları ayrı çıkar" maddesi bu adımda birlikte çözüldü.
- `match` komutu `resolve()` kullanıyor (decompose satırı + sinyal sütunları + `[P]` parent-filtre
  bayrağı gösterir). `--hybrid` bayrağı kaldırıldı (resolve() her zaman BM25+kNN kullanıyor).
- `normalize/query_pipeline.py`'deki kullanılmayan `strip_subunit_only_terms` (eski, sabit-liste
  tabanlı denemenin kalıntısı) silindi — `decompose()` onun yerini aldı.

Ölçüm: `docker/` ES ayaktayken CLI ile canlı doğrulandı — bkz. `inres3 match "..."`. Tüm testler
(108) yeşil. **Henüz gerçek etiketli sette recall ölçülmedi** (F2, aşağıda) — bu sadece canlı
örnek/manuel doğrulama, sistematik değil.

### 1b. Çoklu-hipotez revizyonu (2026-07-23) ✅ BİTTİ — "karar değil hipotez"

> **TAM RAPOR:** `RAPOR_2026-07-23_coklu_hipotez_revizyonu.md` — bulunan 9 hata
> sınıfı kanıtlarıyla, dosya dosya değişiklikler, 30-sorgu önce/sonra tablosu.

**Strateji kararı (kullanıcı): F2 (etiketli set) YAPILMAYACAK.** Sonuç: retrieval'da
incelik ayarı/seçim optimizasyonu tamamen bırakıldı — retrieval'ın tek görevi
**recall'ü korumak**, seçim bütünüyle F4 LLM hakeme geçiyor (hakem sorgu başına
tek tek denetlenebilir, küme-metriği gerektirmez).

Yapılanlar (tümü test-kilitli, 119 test yeşil):
- `decompose` artık TEK sınır SEÇMİYOR: farklı parent'lara işaret eden en iyi
  `MAX_HYPOTHESES=5` sınır hipotezi (`DecomposedQuery.hypotheses`; birincil
  alanlar = hypotheses[0], geriye dönük uyumlu). Sıralanır ama ELENMEZ —
  dünkü geri alınan "doğrulama/seçim" deneyinin tuzağı tekrarlanmadı.
- **Alias-farkındalıklı sınır skoru:** ratio artık name + HER alias'a (ve
  alias'ların virgül-segmentlerine, ≥2 kelime şartıyla) karşı tek tek
  hesaplanıyor. Kanıtlı kaçak sınıfı çözüldü: "JAMSTEC", "Westfälische
  Wilhelm University" (ES alias'tan buluyordu ama name-ratio düşük kalınca
  hipotez doğmuyordu). Bunun için ES belgesine aramaya KAPALI `aliases`
  listesi eklendi (mappings+document, reindex yapıldı). Birleşik
  `aliases_text`'e partial_ratio bilerek KULLANILMADI (jenerik pencere tuzağı).
- decompose `top_k` 5→10 (kısa fuzzy-junk adlar, alan-uzunluğu normuyla doğru
  kaydın exact-alias eşleşmesini top-5 dışına itiyordu — canlı ölçüldü).
- `resolve`: parent havuzu = hipotezlerin birleşimi (birincil `size`, diğerleri
  +3 yeni aday); hipotez parent'ı havuz top-K'sına girmediyse asgari sinyalle
  ENJEKTE edilir (`from_hypothesis_only`); cascade tek parent değil
  `terms: [≤6 parent_id]`. Parent sinyalleri (tsr/qualifier) TAM sorguya karşı
  (hipotez parçasına karşı hesaplanınca jenerik parça alakasız adaylara
  tsr=100 veriyordu).
- Bilinen yan etki (kabul edildi): tek-tokenlik pencereler akronim alias'larına
  tesadüfen 100 alabiliyor ("Ana"→ANA Aeroportos H0 olabiliyor). Formdan
  ayırt edilemez; MAX_HYPOTHESES=5 doğru hipotezi listede tutuyor, seçim
  hakemin işi. 30-sorgu duman testi (`isimler_tekrarsız.csv`, seed 42, gözle):
  net recall başarısı ~24/30, kalan ~6'sı korpusta-hiç-yok (doğru cevap
  no_match) — retrieval kaçağı olarak yalnız İngilizce-alias'ı-veride-olmayan
  vakalar kaldı (ör. Adli Tıp Kurumu'nun "Council of Forensic Medicine"
  alias'ı yok — veri eksikliği, kod değil).

### 2. Deterministik gate (F3 kalan)
Çok net → auto adayı, çok çöp (lexical floor düşük) → no_match. **Eşikler F4'ten SONRA, gerçek sette ayarlanır** (körlemesine değil).

### 3. F2 — recall ölçümü  [İPTAL — kullanıcı kararı 2026-07-23: etiketli set YAPILMAYACAK]
Yerine: retrieval recall-yönelimli tutulur (1b), seçim F4 hakeme bırakılır, doğrulama
sorgu başına gözle/duman testiyle yapılır. (v2 `real_labeled.csv` HATALI, kullanma.)

### 4. F4 — LLM hakem  ✅ BİTTİ (2026-07-24)

**Claude/Anthropic bu katmanda KULLANILMIYOR** (kullanıcı kararı, maliyet —
proje şirkete ait, canlıya (API endpoint) alınacak gerçek bir sistem).
Yerine: **Gemma 4** (Google, 2026-04, Apache 2.0), yerelde **Ollama** üzerinden
(`gemma4:e2b`/`gemma4:e4b` — Ollama'nın kendi kütüphanesi; `hf.co/google/...`
DOĞRUDAN import Ollama 0.32.3'te "gemma4" mimarisi için 400 hatası verdi,
kullanılmadı).

**Tasarım (Pécs örneği tartışması, korunan kararlar):**
- Hipotezler yalnız PARENT sınırı hipotezidir; hakeme HAM METİN verilir (tam
  orijinal sorgu + her hipotezin kurum kısmı) — ÖN-YAPILANDIRMA YOK (virgül-
  segmentasyonu dahil). "Hangi kelime birim, hangisi konum/çöp" ayrımını LLM
  ham metinden kendisi yapar.
- Karar parent ve subunit için AYRI (`JudgeResult.parent` + opsiyonel
  `JudgeResult.subunit`; `subunit=None` = "sorguda hiç istenmedi", ayrı bir
  şey `SubunitDecision(verdict="no_match")` = "istendi ama katalogda yok").
  `parent=auto_match + subunit=no_match` birinci sınıf, geçerli bir sonuç.
- Aday paketine `country/city/kind_label/parent_name` girdi (subunit'in
  country/city'si YOK — ES şemasına dokunmadan, aynı `resolve()` çağrısındaki
  parent listesinden `parent_id` ile JOIN edilir, bkz. `judge/candidates.py`).
- Kosinüs bandı dar uyarısı prompt'ta var (`judge/prompt.py`).

**Modül yapısı (`judge/`):** `client.py` (Ollama HTTP, kalıcı `httpx.Client`,
`LlmClient` Protocol — saglayicidan bagimsiz) · `candidates.py` (aday paketleme)
· `prompt.py` (ham-metin prompt) · `schema.py` (`JudgeResult` pydantic, id
int/"null"-string normalizasyonu) · `judge.py` (orkestrasyon + halüsinasyon-id
doğrulayıcı + anlaşılır Türkçe hata mesajları — pydantic'in ham jargonu
kullanıcıya sızdırılmaz, bkz. `_format_validation_error`). CLI: `inres3 judge
"<sorgu>" [--model] [--top]` (süre + isim+id gösterir, hata durumunda düzgün
mesajla `Exit(1)`, traceback değil).

**Model seçimi — E2B vs E4B (50-sorgu karşılaştırması):**
> **TAM RAPOR:** `DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md` — `isimler_
> tekrarsız.csv`den seed=42, 5 kategoriye (kurum+birim/sadece-kurum/kurum-
> ortada/TR/EN) stratifiye 50 sorgu, tüm ham sonuçlar tablo halinde.

**E2B seçildi:** daha hızlı (~25s→~5-8s/çağrı sıcak, düzeltmelerden sonra ~2.6-3s)
VE şema-uyumu daha yüksek (düzeltme sonrası 44/50 vs E4B 38/50 geçerli çıktı).
Ama E2B'nin en az bir açık örnekte (şirket-adı sorgusu "MPG Makine...") E4B'den
daha kötü muhakeme ettiği görüldü (E2B yanlış auto_match, E4B doğru no_match) —
karar hız/format lehine verildi, muhakeme kalitesi konusunda E4B'den kesin
üstün olmadığı bilinerek. **E4B yerel Ollama'dan silindi** (`ollama rm gemma4:e4b`).

**Performans teşhisi ve düzeltmeleri (2026-07-24, kullanıcı talebiyle):**
- **Gerçek hata (düzeltildi):** `client.py` her çağrıda `httpx.post()` (havuzsuz,
  tek-atış) kullanıyordu — kalıcı `httpx.Client`e geçilince duvar-saati/Ollama'nın
  kendi `total_duration`'ı farkı 5-8s'den 0.01s'ye düştü.
  Ayrıca 50-sorgu testinde E2B↔E4B ARDIŞIK çağrılıyordu — ikisi VRAM'e (11.8GB)
  birden sığmadığı (7.2+9.6=16.8GB) için HER geçişte 7-23s model yeniden yükleme
  maliyeti oluşuyordu; production'da TEK model kullanılınca bu sorun kalmıyor.
- **Ruled out (bug değil):** Ollama zaten HTTP API ile çağrılıyordu (subprocess
  değil); "thinking modu" bu model/sürümde ölçülebilir bir token maliyeti
  yaratmıyor (`think=true/false` fark etmedi); ES client'ı paylaşmak sadece
  ~1ms fark yaratıyor (reconnect sorunu YOK).
- **`decompose()` O(n²) gerçek ve kanıtlı** (bug değil, algoritmik): 5 token→0.4s,
  20 token→9.6s. Bilinen açık madde (aşağıda, `_msearch` batch'leme) — bu oturumda
  DOKUNULMADI.
- **`reasoning` alanı KALDIRILDI** (kullanıcı kararı, hız): sade `verdict+
  matched_id` yeterli; üretilen token ~200→~87'ye düştü, sıcak LLM çağrısı
  ~5-8s→~2.6-3s'ye indi. review/ambiguous durumlarda "neden emin değil"
  bilgisi kaybı bilinen bir ödün (decide/ katmanında ihtiyaç çıkarsa geri
  gelebilir).
- **Sonuç (tipik kısa/orta sorgu, tek model, sıcak):** ~33s/satır → **~4-7s/satır**
  (resolve ~1-4s + LLM ~2.6-3s). Uzun sorgularda (20+ token) decompose'un O(n²)
  maliyeti hâlâ baskın.

**Bağımlılık/config değişiklikleri:** `pyproject.toml` `llm` extra'sı
`anthropic`→`httpx`. `config/default.yaml` `judge.model: "gemma4:e2b"`,
`judge.backend: "ollama"`, `judge.host`. `judge.enabled` hâlâ `false` (F5 batch
entegrasyonundan önce açılacak).

**Yan not (ortam):** `brew install ollama`, bağımlılık olarak `python@3.14`
kurup `/opt/homebrew/bin/python3`'ü projenin asıl Python'unun (python.org
Framework build) önüne geçirdi — `brew unlink python@3.14` ile düzeltildi.
Gelecekte benzer bir `brew install` sonrası `python3`/`pip` beklenmedik
davranırsa önce `which python3` kontrol edilmeli.

**Kalan (F4 kapsamı dışı, bilerek ertelendi):**
- "Yetki asimetrisi" (LLM auto'ya terfi edebilir mi?) — `decide/` katmanı
  henüz yazılmadı, hâlâ açık karar.
- Gate katmanı (F3 kalan) yok — her sorgu LLM'e gidiyor.
- Hata durumunda retry/fallback davranışı tanımsız (CLI şu an sadece düzgün
  mesajla duruyor, otomatik bir şey yapmıyor).
- `decompose()` batch'leme (`_msearch`) — uzun sorgularda hâlâ en büyük tekil
  yavaşlık kaynağı.

### 5. F5 — batch (resume/memoization) + çıktı + EXPERIMENTS günlüğü

### Aday iyileştirme — sol/sağ artık kanalı (kullanıcı fikri) → ÖLÇÜLDÜ, EKLENMEDİ (2026-07-23)
Fikir: kurum sorgunun ortasındayken hipotezin SOL ve SAĞ artıkları ayrı ayrı
aranıp (BM25+kNN) subunit havuzuna katılsın (tam-sorgu araması uzun sorgularda
seyreliyor; iki artığı yapıştırmak embedding'i bulandırır).

**Prototip ölçümü (30-sorgu seti, kod tabanına dokunmadan):** sol/sağ kolların
mevcut havuzun (tam-sorgu, top-10) DIŞINDA getirdiği yeni adaylar sorgu sorgu
gözle değerlendirildi. Sonuç:
- 27-28/30: yeni adayların tamamı AYNI ADLI birimin BAŞKA üniversitelerdeki
  kopyaları (sistematik gürültü deseni). Kök neden: artık parçada parent adı
  kalmıyor → subunit belgelerindeki parent_name enjeksiyonu çıpası kayboluyor,
  sonuçlar tüm üniversitelere saçılıyor. Tam-sorgu kolu bu çıpayı koruduğu
  için doğru cevap zaten 24+/30'da havuzdaydı; sol/sağ hiçbirinde kaçağı
  kurtarmadı.
- 1/30 sınır kazanımı (#30 Afyon): sorgu "Afyon Kocatepe Üniv. Tıp Fak.
  Anesteziyoloji..." diyor ama AKÜ Tıp gerçekte AFYONKARAHİSAR SAĞLIK BİLİMLERİ
  ÜNİVERSİTESİ'ne ayrılmış — doğru birim (Anesteziyoloji AD ← AFSBÜ) baseline
  top-10'da yok, SAĞ kolu getirdi. Bu "kurum yeniden yapılanması" vaka sınıfı
  gerçek ama sol/sağ kanalın genel gürültü maliyetini (sorgu başına +2-4 arama
  + havuza ~5-10 çöp aday → hakem token maliyeti) karşılamıyor.
**Karar: standart kanal olarak EKLENMEDİ.** Yeniden-yapılanma sınıfı için not:
hakem "havuzda doğru yok" dediğinde ikinci-tur parent'sız birim araması
(fallback) daha hedefli bir çözüm olabilir — F4 sonrası değerlendirilecek.

### Açık kararlar (henüz verilmedi)
- **Çok-kurumlu tek kayıt — kaynak veri defekti (bulundu 2026-07-30, ERTELENDİ):**
  Tek bir parent kaydı, birbirinden bağımsız kurumların adlarını alias olarak
  taşıyor. Kanıt: id=810 `Ministerio de Salud` (CR) içinde `Sağlık Bakanlığı`,
  `Ontario Ministry of Health`, `Uganda Ministry of Health`, `Kementerian
  Kesihatan Malaysia` …; id=11875 `Ministry of Justice` (ME) içinde `Adalet
  Bakanlığı` ve `Ministerstvo spravedlnosti České republiky`.
  **Bizim pipeline'ımızda oluşmuyor:** ham `data/raw/institution_parent.csv`
  id=810 satırında 82 alias zaten böyle geliyor (57'si `source: ror`),
  `legacy_institution_ids: []` — birleştirme bizde değil, kaynakta.
  **Sadece bakanlıklarda değil** — aynı desen hastanelerde (`St. Francis
  Hospital` US, `St Mary's Hospital` JP, `St. Luke's Hospital` US), şirketlerde
  (`HSBC`), üniversitelerde (`National University of Science and Technology` OM)
  ve akronim kayıtlarında (`SRC`, `SRI`, `(ISC)²`) da var. Ortak nokta bakanlık
  olmak değil, adın tek başına kimlik belirtmemesi.
  **Tespit için kullanılabilir kanıt (sözlük/eşik gerektirmez):** verinin kendi
  `locale` etiketi — aynı dil altında birden fazla FARKLI ad. Meşru çok-dilli
  kayıtta her dile bir ad düşer (University of Vienna: 0 çakışma), çökmüş
  kayıtta yığılır. Dağılım: bir dilde 2 ad 20.090 kayıt (çoğu meşru: eski ad /
  yazım varyantı), 3 ad 2.715, 4 ad 177, 5+ ad 14. Eşik SEÇİLMEDİ — kesim
  kullanıcı kararı.
  **Etkisi (ölçüldü):** alias arama kanalı (2026-07-30) bu kayıtları havuzda
  görünür yaptı; eskiden birleşik `aliases_text`in uzunluk normu onları
  gömüyordu. Sonuç: `SAĞLIK BAKANLIĞI` → `auto_match` Ministerio de Salud (CR),
  `İçişleri Bakanlığı Göç İdaresi` → `auto_match` Ministry of the Interior (EE);
  ikisi de gold'da `no_match`. Benchmark'ta gold `no_match` doğruluğu 8/39 → 7/39.
  Bunlar gate'ten auto çıktığı için **hakem hiç görmüyor**.
  **Denenip BIRAKILAN yaklaşımlar (tekrar denenmesin):** (a) "çok alias taşıyan
  kayıt" vekili — eşik keyfi, University of Vienna gibi meşru kayıtları
  işaretliyor; (b) ayırt edici token paylaşımına göre "kopuk aile" sayısı — meşru
  çeviriler de kopuk çıkıyor (Belarusian State Technological University); (c)
  korpustan öğrenilen ülke/şehir belirteci — dil kelimeleri (`della`, `conseil`,
  `universität`) yer belirteci sanılıyor, frekansla ayrılmıyor (`della` df=48 vs
  `uganda` df=56). Kullanıcı kararı: sözlük/eşik tabanlı sezgisel yaklaşım YOK.
- **Çapraz-kaynak parent ikizleri (ölçüldü 2026-07-23, ERTELENDİ — F5/batch ÖNCESİ şart):**
  ~270 grup YÖK↔ROR aynı-alias parent çifti (ör. SBÜ 49 ↔ University of Health
  Sciences 8701; Bartın 243↔68525). Bir kısmı SAHTE ikiz (Polis Akademisi TR ↔
  Policijska akademija HR) — ayrım country ile. Plan: decide katmanında
  `parent_equivalents` eşdeğerlik tablosu (alias-eşleşme + aynı country → kanonik
  id, tercihen YÖK), ingest'e dokunmadan, son-işlem çevirisi. F4'ü ENGELLEMEZ.
- LLM auto'ya terfi edebilir mi (yetki asimetrisi)?
- (İÖ) ikizleri: sert-merge mi yumuşak-tercih mi?
- Batch ölçeği/bütçe?
- `decompose()`'un ürettiği T ES-round-trip'i (sorgu token sayısı kadar) F5 batch ölçeğinde
  performans sorunu olur mu — olursa ES `_msearch` ile batch'lenebilir (henüz gerekmedi).

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

# LLM hakem (F4) - Ollama + Gemma 4 E2B yerelde kurulu olmali
brew install ollama && brew services start ollama
ollama pull gemma4:e2b              # hf.co/ dogrudan-import DEGIL, curated tag
inres3 judge "gazi üniversitesi istatistik bölümü" --model gemma4:e2b

# testler
python3 -m pytest tests/unit -q     # 135 test (llm-marked testler Ollama calisiyorsa gercek cagri yapar, yoksa skip)
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
- `elastic/mappings.py` `document.py` `search.py` — ES katmanı (`search`/`search_knn`/`search_hybrid`,
  `extra_filters` ile parent_id cascade filtresi destekler)
- `retrieve/decompose.py` — ES-destekli kurum/birim sınır tespiti (kural değil, korpusa sorma)
- `retrieve/resolve.py` — parent-first cascade + sinyaller (`ScoredCandidate`)
- `judge/client.py` — Ollama HTTP client (kalıcı bağlantı, `LlmClient` Protocol)
- `judge/candidates.py` `prompt.py` `schema.py` `judge.py` — F4 hakem: aday paketleme,
  ham-metin prompt, pydantic çıktı şeması, orkestrasyon+doğrulayıcı
- `docs/DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md` — E2B/E4B model seçimi kanıtı
- `docs/V3_BASLANGIC_REHBERI.md` `V3_VERI_PLANI.md` — orijinal tasarım (ilham, şartname değil)

## Çalışma tarzı (önemli)

Plan dosyaları **ilham/girdi**, körü körüne uygulanacak şartname değil. Her önemli
kararı önce **tartış**, ham veriden **doğrula**, kullanıcı onayını al, sonra kod yaz.
Her kural kendi testiyle doğar.
