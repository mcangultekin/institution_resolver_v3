# DURUM ve PLAN — Institution Resolver v3

> Bu dosya devamlılık içindir: oturum kapanıp açılsa da (veya yeni bir Claude
> oturumu) buradan tam bağlamı alır. Güncel tut. Son güncelleme: 2026-07-23.

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
| **retrieve/ katmanı** | `decompose.py` (ES-destekli sınır tespiti) + `resolve.py` (parent-first cascade + sinyaller) | ✅ BİTTİ (bkz. aşağıda) |
| **retrieve/ 1b** | Çoklu-hipotez + alias-farkındalıklı decompose + çoklu-parent cascade | ✅ BİTTİ (2026-07-23) |
| **F2** | Gerçek sette recall@k ölç | ❌ İPTAL (kullanıcı kararı — bkz. Sıradaki İşler 3) |
| F3 (kalan) | deterministik gate | — |
| F4 | LLM hakem katmanı (tek çağrı parse+judge) + doğrulayıcılar + gerçek sette ölç | — |
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

### 4. F4 — LLM hakem  [ANTHROPIC API GEREKTİRİR]
Adaylar + sinyaller → LLM doğru olanı seçer → `auto_match/review/ambiguous/no_match` + JSON.
Yetki asimetrisi (LLM düşürür, deterministik kanıt yükseltir) — karar bekliyor.

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

# testler
python3 -m pytest tests/unit -q     # 108 test
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
- `docs/V3_BASLANGIC_REHBERI.md` `V3_VERI_PLANI.md` — orijinal tasarım (ilham, şartname değil)

## Çalışma tarzı (önemli)

Plan dosyaları **ilham/girdi**, körü körüne uygulanacak şartname değil. Her önemli
kararı önce **tartış**, ham veriden **doğrula**, kullanıcı onayını al, sonra kod yaz.
Her kural kendi testiyle doğar.
