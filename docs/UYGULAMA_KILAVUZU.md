# Uygulama Kılavuzu — Faz 4: Retrospektif Sonrası Yol Haritası (ES korunuyor)

> Tarih: 2026-07-17. Dayanak: `FABLE_RETROSPEKTIF.md` (Bölüm 5-6) + EXPERIMENTS.md
> tarihçesi. Karar: **Elasticsearch'te kalınıyor** — ES'ten çıkma gerekçeleri v2
> içinde zaten ödendi (ham skor retrofit'i, determinizm, `_source`, paralellik);
> bu kılavuz mevcut ES mimarisi üzerinde ilerler.
>
> Kapsam: 5 adım, bağımlılık sırasıyla. Her adımın "kabul kanıtı" bölümü,
> ACTION_PLAN.md'deki regresyon-kapısı geleneğinin devamıdır.

---

## Değişmez kurallar (her adımda geçerli — ACTION_PLAN mirası)

1. **Kritik kısıt:** auto_match iç doğruluğu hiçbir kabul edilen değişiklikte
   taban değerin altına düşmez. Güncel taban: **seed=42 → %100 (491/491),
   seed=7 → %100 (430/430)** (Faz 3.4 resmî doğrulaması).
2. **seed=42 ayar seti, seed=7 held-out** — seed=7 yalnız adım-sonu kabulde,
   bir kez koşulur (EXPERIMENTS.md başındaki metodoloji kuralı).
3. Ağırlık ve eşik asla ayrı commit'lerde değişmez.
4. Reindex gerektiren işler tek turda toplanır.
5. Her davranış değişikliği: önce kırmızı test → yeşil test + önce/sonra eval
   → EXPERIMENTS.md'ye bölüm.
6. **Yasaklı yollar** (kanıtla kapatıldı, yeniden açma):
   - Klonları *ayırt etme* denemeleri (canonical_ref / grup boyu / skor farkı /
     embedding mesafesi) — Faz 3.5 yapısal imkânsızlıkla kapattı.
   - Kısıtsız (taban-ağırlıksız) öğrenilmiş ağırlık — Faz 3.3 seed=7'de
     kritik kısıtı ihlal etti (IDA/ADA/IPM).
   - Cross-encoder (3.8) — Adım 1-4 bitip gerçek sette plato kanıtlanmadan açılmaz.

**Başlamadan ortam kontrolü:**

```bash
cd docker && docker compose up -d && cd ..     # ES ayakta
.venv/bin/pytest tests/unit -q                 # 236/236 yeşil beklenir
.venv/bin/pytest tests/integration -m integration -q   # 5/5 (canlı ES ister)
```

---

## ADIM 0 — Hijyen (yarım saat, risk: sıfır)

CLAUDE.md üçüncü kez bayat: hâlâ "tests altındaki her dosya 0 bayt" diyor;
gerçekte 236 unit + 5 integration test var ve Faz 0-3 kapanmış durumda.

| İş | Efor |
|---|---|
| 0.1 CLAUDE.md'nin "test yok" paragrafını güncel durumla değiştir (236 test, Faz 3 kapanışı, FABLE_RETROSPEKTIF.md'ye işaret) | 15 dk |
| 0.2 README yol haritasına Faz 4 işareti; bu kılavuza link | 10 dk |

**Kabul kanıtı:** yok (davranış değişmiyor); `git diff` yalnız doc.

---

## ADIM 1 — Gerçek etiketli set (2A.4 borcu) — HER ŞEYDEN ÖNCE

**Neden önce:** Faz 3 dahil tüm kabuller sentetik gold + seed=7 ile geçildi.
"auto_match %100" iddiasının **gerçek dünya karşılığı hiç ölçülmedi** (bilinen
tek transfer verisi: gold auto ~%18 iken gerçek parent auto %5'ti, Faz 2B
sonrası %17). Adım 2-4'ün hepsinin kabul ölçümü bu sete muhtaç.

### 1.1 Örneklem seçimi (yarım gün)

- Kaynak: `data/inbox/sonuc.csv` (1806 satır, en güncel batch çıktısıyla).
- Boyut: **400 satır** (300-500 bandının ortası).
- **Tabakalı örnekle** — rastgele değil: mevcut karar dağılımından
  auto_match / review / ambiguous / no_match kovalarının her birinden orantılı
  + auto_match kovasını bilerek aşırı-örnekle (kesinlik iddiası orada test
  ediliyor). Örnek dağılım: 100 auto_match, 150 review, 100 ambiguous,
  50 no_match.
- Seçim scripti scratch'te; seçilen satır id'leri
  `data/eval_reports/real_labeled_sample_ids.csv`e yazılır (tekrarlanabilirlik).

### 1.2 Etiketleme (2-3 gün insan işi — darboğaz bu)

- Araç hazır: `inres label-set --input <örneklem.csv>` (Faz 2A.4 için
  yazılmıştı; commit 2224644 parent 'n' seçiminde kurum_degil/parent_belirsiz
  ayrımını da destekliyor).
- Etiket şeması (satır başına):
  - `expected_parent_id` (veya `KURUM_DEGIL` / `BELIRSIZ`)
  - `expected_subunit_id` (veya `YOK` — sorgu parent-seviyesi ise;
    klon grubuna denk geliyorsa **gruptaki herhangi bir id kabul** — Adım 2'nin
    merged_ids mantığıyla uyumlu olması için grup üyelerinden birini yaz,
    değerlendirme grup-farkındalıklı yapılacak)
- **Hızlandırıcı:** LLM ön-etiket + insan onayı. Top-5 aday + sorguyu bir
  LLM'e verip önerilen etiketi insan onaylar/düzeltir — tipik olarak elle
  etiketlemenin 3-5x hızı. (Bu aynı zamanda Adım 4 hakem prompt'unun ilk
  provası olur — çift fayda.)

### 1.3 Değerlendirme yolu (yarım gün kod)

- `cli/evaluate.py`e `--real-set data/eval_reports/real_labeled.csv` bayrağı:
  gold-set üretimini atlar, etiketli satırları koşar, aynı metrik/CI
  altyapısını (2A.2 bootstrap) kullanır.
- Yeni metrikler: **gerçek auto_match kesinliği**, **KURUM_DEGIL satırlarının
  no_match yakalanma oranı**, karar dağılımı.

### Kabul kanıtı (ADIM 1 SONU)

- `data/eval_reports/real_labeled.csv` repoda (kişisel veri içeriyorsa
  gitignore'da tutulur, varlığı EXPERIMENTS.md'de belgelenir).
- `inres evaluate --real-set ...` taban raporu alındı: gerçek auto_match
  kesinliği İLK KEZ sayıyla biliniyor.
- Bu taban, bundan sonraki her adımın kıyas zeminidir — EXPERIMENTS.md'ye
  "Gerçek set taban ölçümü" bölümü yazılır.

**Karar noktası:** Gerçek auto_match kesinliği < %95 çıkarsa Adım 2'ye
geçmeden önce yanlışlar sınıflandırılır (hangi hata sınıfı: klon mu, akronim
mi, çeviri mi, kurum-değil mi) — sonraki adımların sırası bu dağılıma göre
teyit edilir.

---

## ADIM 2 — Klon birleştirme (ingest-merge) + kind_label, TEK reindex turu

**Neden:** 5.333 grup / 13.557 fazla aktif satır margin'i eritiyor; SBÜ
vakalarında auto_match matematiksel imkânsız; ambiguous bandı 635/2250.
Faz 3.5 yalnız "ayırt etme"yi kapattı — **birleştirme hiç denenmedi** ve
imkânsızlık kanıtı onu güçlendiriyor: üyeler hiçbir gözlemlenebilir alanda
farklı değilse ayrı kayıt olarak yarıştırılmaları zaten yanlış; tek birleşik
kayıt ikizine near-tie yazı-turasında kaybedemez (Faz 3'teki geri almanın
kök nedeni tanım gereği ortadan kalkar).

### 2.1 Ingest merge kuralı (1-1,5 gün)

`ingest/loader.py`:

- **Birleştirme koşulu (dar tut):** aynı `(parent_id, normalize(name),
  kind_label)` VE **alias kümesi de özdeş** (locale+source+normalize(metin)
  seviyesinde). Alias'ı farklı olan üyeler birleştirilmez — "bilgi kaybı
  sıfır" garantisi ancak böyle korunur.
- Grup → tek `InstitutionRecord`; kanonik id = **deterministik seçim**
  (en küçük sayısal id). Diğer üyeler `merged_ids: list[str]` alanına.
- `quality_report.json`a yeni sayaç: `merged_clone_groups`,
  `merged_clone_rows` (dedup öncesi/sonrası satır sayıları raporda —
  beklenti: gruplar ~5.3K, emilen satır ~13.5K; birebir çıkmayabilir çünkü
  alias-özdeşlik şartı bazı grupları böler — gerçek sayı ölçülüp yazılır).
- Self-parent filtresi (Sorun 1B) aynen korunur, merge ondan SONRA çalışır.

### 2.2 ES mapping + çıktı yüzeyi (yarım gün)

- `elastic/mappings.py`: `merged_ids` (keyword listesi) + `kind_label`
  (keyword) alanları. **kind_label bu turda yalnız index + görüntüleme +
  filtrelenebilirlik** — rerank sinyali DEĞİL (Ö11 qualifier kazancı zaten
  alındı; sinyal denemesi ayrı, ölçümlü bir iş olarak sonraya).
- `resolver.py` / `MatchResult`: aday çıktısına `merged_ids` ve `kind_label`
  taşınır; `cli/batch.py` çıktı CSV'sine `merged_ids` kolonu (dolu ise
  `;` ile ayrılmış liste).

### 2.3 Eval grup-farkındalığı (yarım gün)

- `eval/metrics.py` (veya karşılaştırma noktası neresiyse):
  `predicted_id == expected_id` yerine
  `expected_id ∈ ({predicted_id} ∪ predicted.merged_ids)` doğru sayılır.
- Birim test: birleşik kayda düşen expected için top-1 doğru sayılıyor;
  birleşmemiş kayıtta davranış değişmiyor.

### 2.4 (Opsiyonel, aynı tura biner) zincirli-ad ilk segment temizliği

Zincirli 2.802 addan kendi parent adıyla başlayan ~134-704 kayıtta embed
metnine parent adının İKİ kez girmesini önle (ilk segment parent'la
eşleşiyorsa embed-metninden düşür; alias olarak tam zincir kalır).
Küçük iş, küçük etki (≤%0.9 kayıt) — sadece bu reindex turuna binebildiği
için buraya; ayrı tur AÇMAZ.

### 2.5 Tek reindex + doğrulama

```bash
inres index --force-recreate    # embed metni değişmiyorsa cache isabet eder (~6 dk;
                                # 2.4 yapılırsa etkilenen kayıtlar yeniden encode edilir)
.venv/bin/pytest tests/unit -q
.venv/bin/pytest tests/integration -m integration -q   # determinizm testi dahil
```

Canlı smoke (EXPERIMENTS'teki bilinen vakalar):

- `"Sağlık Bilimleri Üniversitesi Yoğun Bakım Bilim Dalı"` → top-5 artık 165
  klon değil; marj > 0.10 beklenir; karar review/auto (skor kapısına bağlı).
- `"Manisa Celal Bayar Üniversitesi Bilgisayar Bilimleri Anabilim Dalı"` →
  marj eski 0.0036'nın çok üstünde.
- Çankırı `"TASARIM BÖLÜMÜ"` ikizi: iki kayıt alias'larına kadar özdeşse tek
  kayda birleşmiş olmalı (Faz 3'ün yazı-tura vakası tanım gereği yok).

### Kabul kanıtı (ADIM 2 SONU — regresyon kapısı)

1. Testler: unit tamamı + integration (determinizm dahil) yeşil.
2. Tam eval **seed=42** + **seed=7** (tek koşu): auto_match iç doğruluk
   **%100/%100 korunur** (taban). auto_match n ve ambiguous n raporlanır —
   beklenti: ambiguous 635'ten belirgin aşağı, auto_match yukarı; ama kabul
   kriteri yalnız iç doğruluk + "hiçbir top-1/top-5 CI-dışı gerilemez".
3. **Gerçek set (Adım 1)** yeniden koşulur: kesinlik tabanın altına düşmez,
   klon-kaynaklı ambiguous/review satırlarının yeni kararları elle örneklenir
   (20 örnek).
4. Sonuç EXPERIMENTS.md'ye; sayılar (kaç grup birleşti, kaç satır emildi)
   quality raporundan aktarılır.

**Geri alma tetiği:** herhangi bir seed'de iç doğruluk < %100 → Faz 3'teki
disiplinle önce kök neden, düzelmiyorsa geri al. (Beklenmiyor — near-tie
mekanizması yapısal olarak kalktı — ama kural kuraldır.)

---

## ADIM 3 — Eşiklerin record_type'a ayrılması (1-2 gün)

**Neden:** Faz 3.3'te ölçülen maliyet: eşik paylaşımlı olduğu için parent'ı
memnun eden 0.92→0.934 yükselişi subunit auto_match hacminin %12'sini sildi.
Ağırlıklar zaten ayrı (3.2); eşiklerin ayrılmaması yarım kalmış simetri.

### 3.1 Uygulama

- `config/default.yaml`: `decision.thresholds` →
  `thresholds_parent` / `thresholds_subunit` (her birinde `auto_match_score`,
  `auto_match_margin`, `review_score`, `min_absolute_lexical_floor`).
  Başlangıç değerleri mevcutla birebir aynı kopyalanır (Faz 3.2 deseni:
  önce mimari, sonra değer).
- `decide/policy.py`: `decide(..., record_type=...)` — resolver iki çağrıda
  zaten hangi tarafta olduğunu biliyor.
- Birim test: parent eşiği değişince subunit kararı bit-bit sabit (3.2'deki
  `TestWeightsByRecordType` deseninin eşik ikizi).

### 3.2 Kalibrasyon (capture-once + local sweep — Faz 3.3 Adım 5 yöntemi)

- seed=42'den n≈600 sorgu için ES'e BİR kez sorulup adaylar pickle'lanır;
  sweep yerel. Parent ve subunit eşiği ayrı taranır.
- Hedef: her iki tarafta iç doğruluk %100 kalırken hacim maksimize; özellikle
  subunit'te 3.3'te feda edilen hacmin geri kazanımı.
- **Gerçek set (Adım 1) sweep'e dahil edilir** — eşik artık yalnız sentetik
  kümelenmeye göre seçilmez (K5'in asıl amacı buydu).

### Kabul kanıtı (ADIM 3 SONU)

- seed=42 + seed=7 (tek koşu) + gerçek set: iç doğruluk tabanın altına
  düşmez; subunit auto_match hacim değişimi raporlanır.
- Ağırlıklara DOKUNULMADI (bu adım yalnız eşik) — kural 3 gereği tek commit'te
  yalnız eşik değişiyor olması serbest (ağırlık sabit kaldığı sürece).

---

## ADIM 4 — LLM hakem POC'u (review bandı) (3-5 gün)

**Neden:** Gerçek veride parent kararlarının %68'i hâlâ review — karar kütlesi
orada yaşıyor. Lineer sistemin kanıtla çözemediği sınıfların bir kısmı
(Ticaret↔Commerce çeviri çiftleri, "kurum değil" gri bandı 0.60-0.90,
KTU-tipi çok-ülke akronim belirsizliği) tam olarak bir hakem-LLM'in güçlü
olduğu işler.

### 4.1 Kapsam sınırları (baştan sabitle)

- Hakem **yalnız `review` kararlarını** görür. `auto_match`e dokunmaz
  (kritik kısıt yapısal olarak korunur — floor-kapısı deseniyle aynı mantık).
- Hakem çıktısı üç değerli: `CONFIRM` (top-1 doğru → auto'ya terfi önerisi),
  `NOT_INSTITUTION` (→ no_match önerisi), `UNCERTAIN` (review'da kalır).
- **Klon gruplarından beklenti kurulmaz:** ayırt edici bilgi metinde yok —
  Faz 3.5 kanıtı hakem için de geçerli; klon-grubuna düşen review'lar
  hakeme hiç gönderilmeyebilir (merged_ids zaten Adım 2'de bunları tekilleştirdi).

### 4.2 Uygulama iskeleti

- Yeni modül `judge/` (rerank/decide'a sızmaz — katman ayrımı korunur):
  girdi = sorgu + top-5 aday (display_name, parent adı, matched_alias,
  skor, sinyal kırılımı) → tek LLM çağrısı → üç-değerli karar + gerekçe.
- CLI: `inres batch --judge` bayrağı (varsayılan kapalı); çıktıya
  `judge_verdict`, `judge_reason` kolonları. Batch'te asenkron/toplu çağrı,
  maliyet loglanır.
- Model: küçük/ucuz bir model yeterli olmalı (kısa metin, kapalı seçenek
  kümesi); prompt Adım 1.2'deki ön-etiketleme deneyiminden türetilir.

### 4.3 Ölçüm (gerçek set üzerinde A/B — Adım 1 olmadan bu adım ANLAMSIZ)

| Metrik | Tanım |
|---|---|
| Terfi kesinliği | hakem CONFIRM dediklerinin gerçekte doğru oranı — hedef ≥ mevcut auto_match kesinliği |
| Tenzil isabeti | NOT_INSTITUTION dediklerinin gerçekte kurum-dışı oranı |
| Hacim etkisi | review havuzunun küçülme oranı |
| Maliyet | 1000 satır başına $ + saniye |

### Kabul kanıtı (ADIM 4 SONU)

- Gerçek sette A/B raporu EXPERIMENTS.md'de. Terfi kesinliği auto_match
  kesinliğinin altındaysa hakem yalnız `NOT_INSTITUTION` yönünde kullanılır
  (tek yönlü hakem de değerlidir) ya da POC gerekçeli kapatılır.
- Hakem hiçbir koşulda `decide()`ın kendisine gömülmez — ayrı katman,
  bayrakla açılır.

---

## ADIM 5 — v3 karar noktası (yeniden değerlendirme — iş değil, karar)

Adım 1-4 bittiğinde elde ilk kez şunlar olacak: gerçek sette ölçülmüş
kesinlik/hacim, klonsuz margin dağılımı, record_type-ayrı eşikler, hakemli
review bandı. **Ancak bu noktada** "tavan iş hedefini karşılıyor mu" sorusu
meşru biçimde sorulabilir:

- **Karşılıyorsa:** v2'de kalınır; kalan işler operasyonel (Ö10 chunk'lı
  indexleme yalnız veri 10x büyürse, cross-encoder yalnız gerçek sette plato
  kanıtlanırsa).
- **Karşılamıyorsa ve açık mimariyse:** REBUILD_GUIDE Bölüm 2+4 +
  FABLE_RETROSPEKTIF Bölüm 4 taslağıyla v3 tartışması açılır. Not: bu durumda
  bile ES'te kalınabilir — v3'ün özü tek-korpus/şema/çıktı-tipi kararlarıdır,
  arama motoru değişimi değil.
- Beklentim (retrospektifteki kanıtla): kalan hataların ağırlık merkezi
  veri-sınırlı (paylaşılan adlar, kısa akronimler) — v3 tetiklenmez, iş
  hedefi "parent-koşullu subunit doğruluğu" gibi verinin çözünürlüğüyle
  uyumlu bir metriğe bağlanır.

---

## Özet zaman çizelgesi

| Adım | İçerik | Efor | Ana çıktı |
|---|---|---|---|
| 0 | CLAUDE.md/doc hijyeni | 0,5 saat | Doğru talimat dosyası |
| 1 | Gerçek etiketli set + `--real-set` yolu | 3-4 gün (etiketleme dahil) | Gerçek kesinlik İLK KEZ ölçülü |
| 2 | Klon ingest-merge + merged_ids + kind_label index'e (+opsiyonel zincir temizliği), tek reindex | 3-4 gün | Margin-eritici 13.5K satır emildi; ambiguous bandı küçüldü |
| 3 | Eşiklerin record_type'a ayrılması + kalibrasyon | 1-2 gün | Subunit hacim geri kazanımı |
| 4 | LLM hakem POC (review bandı) | 3-5 gün | Review %68'inin triyajı, ölçülü |
| 5 | v3 karar noktası | — (karar) | Kanıtlı devam/pivot kararı |

Toplam: ~2-3 hafta. Sıra bağımlılık sırasıdır: 1 olmadan 2-4'ün kabul ölçümü
yok; 2 olmadan 3'ün sweep'i bozuk margin dağılımına kalibre olur (REBUILD_GUIDE
Adım 2 gerekçesiyle aynı); 4'ün A/B'si 1'in setine muhtaç.
