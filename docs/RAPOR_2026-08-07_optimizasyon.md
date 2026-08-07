# Optimizasyon çalışması — 6–7 Ağustos 2026

**Durum: ERTELENDİ.** Çalışan kod `335f1a9`'a geri alındı; her şey
`opt/arsiv-2026-08-07` dalında (GitHub'da) duruyor. Bu belge çalışmanın
tamamını — planı, uygulananları, reddedilenleri ve *neden*lerini — kaydeder ki
işe geri dönüldüğünde sıfırdan başlanmasın.

---

## 1. Özet

| | |
|---|---|
| Amaç | Sorgu yolunun hızlandırılması |
| Süre bütçesi (ölçülen) | %62 LLM, %33 ES retrieval, %1 Python |
| Uygulanan (arşivde) | Dalga 1 (B1/B2/B4/B5), C2, C4, B10, Colab defteri |
| **Ölçülen kazanç** | retrieval **1,39×**; uçtan uca **%1** (Dalga 1) → **%20** (B10 ile) |
| Ölçülerek **reddedilen** | 5 kalem (B7, kosinüs-prompt, B14, A6, `_source`'tan embedding) |
| Kaydedilen borç | 10 kalem |

**En önemli sonuç:** bu sistemde süre LLM'de, LLM'de de **prompt işlemede
(%85)**. Donanım tavanı ölçüldü: Apple M4, 8 GPU çekirdeği, `gemma4:e4b` için
**232 token/s**. Tek kaldıraç gönderilen token sayısı. Retrieval'ı %28
hızlandırmak uçtan uca yalnızca %1 getirdi; prompt'u %55 kısaltmak %20 getirdi.

---

## 2. Başlangıç ölçümleri

500 sorguluk `decide` koşusundan (`benchmark_500_sample.csv`):

| yol | pay | medyan |
|---|---|---|
| gate (LLM yok) | %42 | 0,60 s |
| judge (LLM'li) | %58 | 24,4 s |

LLM'e gitme nedenleri: %55 ikisi de blokladı, **%34 sadece subunit**, %11
sadece parent.

Profil (`cProfile`, 3 sorgu): ES round-trip **%96**, Python hesabı %1.
Sorgu başına ES trafiği: **2,5–7,6 MB**, 12–16 istek.

Tek belge (`parent:143`) 17.388 B; Python'un okuduğu **156 B (%0,9)**.
Kalanın neredeyse tamamı `embedding` (16.970 B, 768 ondalık sayı JSON metni).

Prompt bileşimi: **sabit talimat bloğu %56**, parent adayları %18,
subunit adayları %17,5, sorgu+hipotezler %8,5.

Ollama iç metrikleri: **prompt işleme %85**, üretim %13, model yükleme %2.

---

## 3. Metodoloji — çalışma boyunca öğrenilenler

Bu bölüm koddan daha değerli olabilir; aynı hatalar tekrarlanmasın.

1. **LLM A/B'leri farklı günlerin CSV'leriyle yapılamaz.** 5 ve 6 Ağustos
   koşuları arasında 42/452 (%9,3) karar farkı çıktı ve bir süre bunu "LLM
   tekrarlanabilir değil" diye yorumladım. **Yanlıştı.** Doğrudan test
   (aynı sorgu × 3 tekrar, × 3 ayrı süreç) LLM'in **deterministik** olduğunu
   gösterdi; prompt'lar da sha256 olarak birebir aynıydı. Fark, iki koşunun
   farklı makine durumlarında yapılmasından geliyor (en güçlü hipotez:
   Ollama'nın model yüklerken o anki boş belleğe göre GPU'ya kaç katman
   koyduğu değişiyor — llama.cpp GPU/CPU çekirdekleri bit-denk değil).
   → **Kıyas art arda, aynı oturumda yapılmalı.**

2. **Küçük örneklem simülasyonu güvenilmez.** B2 için "1,46×" tahmin ettim,
   500 sorguda 1,07× çıktı. B4 için "−118 ms", gerçek −19,6 ms. B5 için "~%1",
   gerçek %5,4. Örüntü: 40–50 sorguluk ölçümden genelleme.
   → **Tahmin verme, 500-sorgu ölçümüne bak.**

3. **KV-cache kirlenmesine dikkat.** Bir prompt'un sonuna karakter eklemek onu
   cache'tekinin *devamı* yapar ve 12,5 s → 0,06 s'ye düşürür. Bu, ölçümü
   sahte şekilde iyi gösterir. Taze prompt kullan.

4. **Sorgu metnini elle yazma.** `Türkiye` yerine `Turkey` yazdığım için bir
   vakayı "tekrarlanamaz" sandım. CSV'den al.

5. **Ölçüm aracının kapsamını bil.** Eşdeğerlik koşumum `resolve+gate`'i
   karşılaştırıyordu; hakemin gördüğü ama gate'in görmediği alanları
   (`country`, `city`, `parent_name`, `kind_label_raw`) hiç kontrol etmiyordu.

6. **`_disk_usage` API'sinin alan-bazlı rakamları toplamla tutarlı değil.**
   `_source`'un %74,9 olduğunu söyledi; `_source`'tan `embedding` çıkarılınca
   o alan 37,4 → 1,1 MB düştü ama **toplam indeks boyutu değişmedi.**

---

## 4. Uygulananlar (arşivde: `opt/arsiv-2026-08-07`)

### 4.1 Dalga 1 — davranış-nötr hızlandırma (`68fb44d`)

| # | Ne | Ölçülen |
|---|---|---|
| **B1** | `normalize()` → `@lru_cache`; `NormalizedName` → `frozen` | 1,16× |
| **B2** | Arama yanıtında `_source` beyaz listesi (9 alan) | 1,07× |
| **B4** | Kosinüs opsiyonel (`with_cosine`, varsayılan kapalı) + CLI/API bayrağı | 1,06× |
| **B5** | `get_client()` → `@lru_cache` | 1,06× |
| | **kümülatif** | **1,39×** (445,9 → 320,2 ms) |

**B1 gerekçesi:** aynı katalog string'i sorgu başına ortalama 7,6 kez yeniden
normalize ediliyordu (1.680 çağrı / 221 benzersiz, %86,8 tekrar). Çağrı başı
18,1 µs → 0,04 µs. `frozen` **önce** gerekli: cache aynı örneği paylaştırdığı
için mutasyon cache'i zehirlerdi (aynı tuzak `query_encoder`'da vektörü
read-only işaretleyerek çözülmüş).

**B2 gerekçesi:** belge 17.388 B, okunan 156 B. `_source` filtresi **aramayı
etkilemez** — arama ters indekse bakar. Liste tüketici taramasıyla çıkarıldı
(`decompose`, `_attach_signals`, `gate`, `resolve`, `candidates`), eksik alan
hata vermez `None` döner, o yüzden testle sabitlendi.

**B4 gerekçesi:** kosinüs **hiçbir karar yoluna girmiyor** — gate'te
`# gosterim`, prompt'tan `814437b` ile çıkarılmış, `decide` bakmıyor. Havuz
sırası da etkilenmez (RRF ham listelerle çalışır). **kNN retrieval aynen
kalır** — parent havuzunun %16,2'si sadece o kanaldan geliyor.

**B5 gerekçesi:** hız değil **kaynak**. Sorgu başına 11–15 yeni `Elasticsearch`
nesnesi; 31 sorgu sonrası **194 açık TCP soketi** (sadece `gc.collect()` ile
1'e düşüyordu). Düzeltme sonrası sabit 2.

**Doğrulama:** 500 sorguda 930 karar alan-alan karşılaştırıldı →
`verdict`/`matched_id`/`confidence`/`tsr`/`exact_match`/`bm25_norm`/`reason` ve
`parent_pool`/`subunit_pool`/`hypotheses` **sıfır fark**. İki ayrı günde
tekrarlandı: gate'in karar verdiği 194 satırda yine sıfır fark.

**Yan kazanımlar:** ES trafiği 7,59 MB → 0,16 MB (**47×**); açık soket 194 → 2.

### 4.2 C4 + C2 (`5cf1533`)

**C4** — `decide_batch`'e `gate_parent_id` / `gate_subunit_id` kolonları.
Bu kolon olmadan *"gate hangi kaydı önermişti, hakeminkiyle aynı mıydı?"*
sorusu cevaplanamıyordu ve iki karar kilitliydi.

**C2** — Ollama'ya **seçici** retry (2 tekrar, üstel backoff).
- Yeniden denenir: `httpx.TransportError` + HTTP 5xx
- **Denenmez:** HTTP 4xx (yanlış model tag'i, bozuk şema) ve prompt-kırpılma
  hatası — tekrar sadece zaman yakar ve gerçek sorunu gizler.

**Sonuç:** 500-sorgu koşusunda bağlantı hatası **10 → 0**. Ölçekte anlamı:
500K kayıtlık üretimde ~10.000 sessizce kaybedilen satır.

### 4.3 B10 — parent-sabitli subunit sorgusu (`488bdcf`, arşivde)

Gate parent'a `auto_match` verdiyse parent sabitlenir, hakeme yalnızca birim
sorulur; şema enum'u **yalnız o parent'ın altındaki** subunit'leri içerir.

**Ölçüm (30 sorgu, aynı oturum A/B):**

| | eski | yeni |
|---|---|---|
| Prompt | 8.221 kar | **3.720 kar** (%55 ↓) |
| LLM süresi (medyan) | 23,13 s | **8,40 s** (**2,75×**) |
| **LLM hiç çağrılmadı** | — | **10/30 (%33)** |
| Subunit karar uyumu | — | 23/30 |

LLM'siz biten 10 sorgunun **10'unda da** eski tam hakem aynı sonuca (`no_match`)
varmıştı — kısayol hatasız.

7 karar farkının **6'sı zararsız**: aynı kayıt, `review` → `auto_match` (kısa
ve odaklı prompt'ta model daha emin). **1 gerileme:** `Tehran azad university`
— `decompose` "Tehran"ı `unit_part` yapıyor, parent bağlamı kalkınca model onu
"West Tehran Branch"e bağlıyor. Eski yol bağlamla telafi ediyordu.

**Uçtan uca etkisi: %20** (121 dk → 97,5 dk).

**Bedeli:** gate'in parent'ı yanlışsa hakem artık düzeltemez. Bu, 2026-07-28'de
alınan "auto değilse sorgunun *tamamı* hakeme gider" kararının bilinçli
revizyonu — o karar "`judge()` bunu desteklemiyor" gerekçesiyle alınmıştı,
doğruluk gerekçesiyle değil.

### 4.4 Colab defteri (`184d7bb`, arşivde)

`notebooks/colab_decide_batch.ipynb` — 33 hücre, sıfırdan. Ham veri, işlenmiş
veri, **embedding cache'i** (712 MB), Ollama modeli ve çıktılar Drive'da.
Sonunda yerelde koşuldu ama defter kullanılabilir durumda.

---

## 5. Reddedilenler — hepsi ölçülerek

### 5.1 B7 — `any_rival_blocks_auto` bayrağını kapat ❌

**Hipotez:** gate `ambiguous` dediği 35 sorguda hakem 35/35 tek adaya
bağlanıyor; bayrak kapatılırsa o sorgular LLM'e hiç gitmez (~14 dk).

**Ölçüm (C4 sayesinde):** gate'in önerdiği id, hakemin seçtiğiyle
**%77 aynı, %23 FARKLI**.

```
Süleyman Demirel Üniv. İİBF   gate=50306 (Kazakistan)  hakem=206 (Türkiye)
Istanbul Univ., Inst. of Soc. gate=26087 (Sırbistan)   hakem=66  (Türkiye)
```

**Karar: RED.** %23 yanlış-auto oranı 14 dakika için kabul edilemez. Gate'in
`ambiguous` demesi doğru davranış.

### 5.2 Kosinüsü prompt'a geri ekle ❌

**Test:** gate ile hakemin farklı kurum seçtiği 14 sorguda kosinüs hangisini
destekliyor?

Doğrulanabilir 3 vakada da **yanlış/yabancı kaydı** destekledi (Kazakistan'daki
SDU'yu, Sırbistan'daki enstitüyü, İngiltere'deki jenerik "State Hospital"ı).
Çözünürlük: medyan Δ=0,030, min Δ=0,003 — kullanılabilir bandın (0,78–0,92)
beşte biri.

Anizotropi doğrulandı: `ATAŞEHİR ADIGÜZEL MYO` kaydına karşı
`bugün hava çok güzel` = 0,796 > `Harvard University` = 0,759.

**Karar: RED.** Prompt'un kendi kuralı *"ülke/şehir tutarlılığı ZORUNLU"*
diyor; kosinüs sistematik olarak onun tersini fısıldıyor. 2026-07-27'deki
kaldırma kararını bağımsız olarak doğrular.

### 5.3 B14 — hakeme giden aday sayısı 8 → 5 ❌

**Ölçüm:** prompt yalnızca **%6** kısalıyor, hız 1,07×. Neden: `resolve(size=5)`
olduğu için subunit havuzu zaten ≤5; kırpma sadece parent listesini etkiliyor.

**Karar: RED.** Karar riski (aday düşürme) marjinal kazanca değmez.

### 5.4 A6 — kullanılmayan `edge` alanını kaldır ❌

`edge_ngram` alt-alanı mapping'de var, **hiçbir sorgu kullanmıyor**
(`grep '\.edge'` → mappings.py dışında sıfır). Ama ölçüldü: tüm `.edge`
alanları indeksin **%0,4'ü** (14 MB / 3,85 GB).

**Karar: RED.** Tam reindex maliyetine değmez. Zararsız ölü ağırlık olarak
kalabilir.

### 5.5 `_source`'tan `embedding`'i hariç tut ❌

**Hipotez:** vektör indekste iki kez duruyor (`_source` JSON'u + dense_vector);
`_source.excludes` ile ~2,8 GB kazanılır.

**Ölçüm (3.000 gerçek belge, simetrik protokol, forcemerge + flush):**

| | disk |
|---|---|
| `_source`'ta embedding var | 50,81 MB |
| hariç tutulmuş | 51,02 MB |
| **fark** | **−0,21 MB (≈ sıfır)** |

kNN aynen çalışıyor, `_source` 30× küçülüyor — ama **toplam indeks boyutu
değişmiyor.**

**Karar: RED.** Erken tahminim (~2,8 GB) tek belgenin ham JSON boyutundan
genellemeydi; sıkıştırma ve ES'in iç saklama biçimi o oranı geçersiz kılıyor.

### 5.6 Priming hilesi ⏸️ (uygulanmadı, belgelendi)

Ollama KV-cache'i **yalnızca yeni prompt cache'tekinin devamıysa** kullanıyor:

```
cache: P     yeni: P + "..."           → 0,05 s   ✅
cache: P1    yeni: P2 (%57 ortak önek) → 15 s     ❌
```

Her çağrıdan önce sabit bloğu ayrıca göndermek cache'i o noktaya geri sarıyor:
15 s → **9,1 s (~%40)**.

**Uygulanmadı:** sorgu başına fazladan API çağrısı + Ollama'nın belgelenmemiş
iç davranışına bağımlılık (sürüm değişince sessizce bozulabilir). Prompt'u
küçültmek aynı kazancı sağlam biçimde verir.

---

## 6. Altyapı bulguları

### 6.1 Docker bellek ayrımı — gerçek bir sorundu

`MemoryMiB = 14336` (17,2 GB'lık makinenin %85'i) iken ES yalnızca 3,6 GB
kullanıyordu. Sonuç: swap 10,8/12,3 GB dolu.

| | 14,6 GB | 5,2 GB |
|---|---|---|
| Swap | 10,8 GB | 0,34 GB |
| Gate | 614 ms | 401 ms |
| Batch tahmini | 97 dk | 51 dk |

**Not:** Ollama zaten native (Homebrew) ve GPU'da çalışıyor — hiç
dockerize edilmemişti. Docker Desktop macOS'ta **GPU ayıramaz**.

### 6.2 Donanım tavanı

Makine tamamen boşken (Docker kapalı, ES kapalı) ölçülen prompt işleme hızı:
**232 token/s** — batch sırasındaki ~200–250 ile aynı. Yani altyapı LLM'i
sınırlamıyordu; bu, Apple M4 (8 GPU çekirdeği) üzerinde 8B/Q4 model için
beklenen değer.

---

## 7. Bulunan ama düzeltilmeyen sorunlar (borç)

1. **`unit_part` = "artık metin", "birim ifadesi" değil.** Kurum aralığının
   dışında kalan her şey oraya düşüyor: `Tehran azad university` → `"Tehran"`,
   `School of allied and healthcare sciences` → `"and"`. `gate.py` bunu birim
   varsayıp subunit araması başlatıyor.
2. **`decompose.py` docstring'i yanlış:** *"bu alan zaten sadece CLI
   gösterimi/hata ayıklama için kullanılıyor"* diyor, ama `gate.py` onu tüketip
   "sorguda birim var mı" kararını veriyor.
3. **Dejenere hipotezler.** Tek kelimelik span'ler alias'lara birebir oturup
   100 puan alarak birincil hipotez olabiliyor (`"and"` → alakasız parent),
   o sorgunun havuzunu baştan bozuyor.
4. **`exact_span` set-sırası belirsizliği.** `_attach_signals` alias'ları
   `set` üzerinde geziyor; bir adayın birden fazla yazımı sorguda geçerse
   hangisinin seçileceği hash rastgeleliğine bağlı. **Ölçüldü:** 926 exact
   eşleşmenin 2'sinde oluşuyor, karar etkisi **0/500**.
5. **Span'ın kıyaslayıcı olarak zayıflığı.** `max(exact, key=(span, tsr))`
   "adı uzun olan kazanır" demek; uzunluk ≠ ayırt edicilik. `_is_short_acronym`
   yaması bu kusurun itirafı.
6. **Kanonik ad ayrıcalığı tutarsızlığı.** `_attach_signals` önce kanonik ada
   bakıp eşleşirse alias'lara hiç bakmıyor — oysa parent arama kanalında bu
   ayrıcalık 2026-07-29'da bilerek kaldırılmıştı.
7. **Kanonik adın alias listesinde olması kod garantisi değil, veri tesadüfü.**
   106.183 parent tarandı: 0 kayıt aranamaz durumda. Ama `document.py` adı
   listeye enjekte etmiyor; ingest bir gün üretmezse o kurum **sessizce**
   görünmez olur. *Öneri: build/index adımına gürültülü bir doğrulama ekle.*
8. **Ölü config anahtarları.** Kodda sıfır referansı olanlar: tüm `retrieval`
   bloğu (`pool_size`, `parent_top_k`, `subunit_top_k`, `rrf.rank_constant`,
   `boosts`), `judge.enabled`, `judge.auto_confidence`, `judge.cache_dir`,
   `decision.auto_precision_target`. `boosts` ayrıca **var olmayan alan
   adları** kullanıyor (`unit_name`, `aliases.normalized`) — yanıltıcı.
9. **Prompt hiç sistematik test edilmedi.** 1.600 token'lık sabit talimat
   bloğu tek tek olaylardan birikmiş; hiçbir kural "token'ını hak ediyor mu"
   diye ölçülmemiş. Zayıf kanıt: B10 için sıfırdan yazılan %55 daha kısa
   prompt kaliteyi düşürmedi, **kalibrasyonu iyileştirdi**.
10. **ES'te ~5,2 GB ölü indeks** (`institutions_parent`, `institutions_subunit`,
    `institutions_v1_yedek_20260729`) — v3 yalnız `institutions_v1` kullanıyor.

---

## 8. İşe geri dönülürse — öncelik sırası

| # | Kalem | Ölçülen/tahmini | Ön koşul |
|---|---|---|---|
| 1 | **B10** (arşivde hazır) | uçtan uca **%20** | `Tehran` gerilemesi için prompt'a *bilgi* ekle (parent sorgunun hangi kısmını tükettiği), kural ekleme |
| 2 | **Dalga 1** (arşivde hazır) | retrieval %28 | Yok — davranış-nötr, doğrulanmış |
| 3 | **C2** (arşivde hazır) | %2 veri kurtarma | Yok |
| 4 | Sabit talimat bloğunu kısaltma | ölçülmedi (%56'lık dilim) | **gold** |
| 5 | Gate kova ayarları (B8/B9) | ~%3–5 | **gold** |
| 6 | Priming hilesi | ~%25–30 | Kırılganlık kabul edilirse |

**Gerçekçi tavan:** mevcut mimari ve bu donanımda **%40–50**. Ötesi ya daha
küçük model (karar değişir — E2B denenip reddedilmişti) ya daha güçlü donanım.

**Önündeki asıl engel gold etiketli set.** Prompt optimizasyonu, gate eşikleri
ve B10'un doğruluk teyidi — üçü de ona bağlı. Bugün ancak *tutarlılık* ve *hız*
ölçülebildi, *doğruluk* değil.

---

## 9. Üretilen kalıcı çıktılar

- `output/decide_baseline_dalga1_2026-08-06.csv` — 500 satır tam baseline
  (467 ok, 33 hata; hepsi kurum/birim uyuşmazlığı, bağlantı hatası 0)
- `opt/arsiv-2026-08-07` dalı — tüm kod, GitHub'da
- Bu rapor
