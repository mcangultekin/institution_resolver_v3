# OpenAlex Kurum Çözümleme Sistemleriyle Karşılaştırma

*2026-08-26*

## Kapsam

`ourresearch` (OpenAlex) GitHub organizasyonunda bizim işimize benzeyen iki repo bulundu:

- **[openalex-institution-parsing](https://github.com/ourresearch/openalex-institution-parsing)** — OpenAlex'in üretimde kullandığı, affiliation string → ROR ID eşleyen eğitilmiş sınıflandırıcı (V1/V2).
- **[institutions-gold-standard](https://github.com/ourresearch/institutions-gold-standard)** — Claude (Sonnet/Opus) ile tool-use kullanarak ROR gold-standard veri seti üreten annotation aracı.

Aşağıda bu iki sistem, `institution_resolver_v3` (bu depo) ile 15 boyutta, 5 kategoride karşılaştırılıyor. OpenAlex tarafında iki alt sistem farklı davrandığında `[parser]` / `[gold]` etiketiyle ayrıştırılmıştır.

---

## Kapsam ve amaç

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Ne çözüyor | Verilen kurum ifadesini iki seviyeli (parent + subunit) katalog kaydına bağlamak. Kurum *çıkarımı* kapsam dışı — ifade zaten elde olmalı. | `[parser]` Eser affiliation string'ini bir veya daha fazla ROR kimliğine bağlamak (uçtan uca, üretimde). `[gold]` ROR gold-standard *veri seti üretmek* — canlı çözümleme değil, etiketleme aracı. |
| Kullanım bağlamı | Şirket içi batch iş + envanter modu; canlıya alınacak ama henüz kapalı devre. | `[parser]` OpenAlex API'sinin arkasında sürekli çalışan üretim bileşeni. `[gold]` Tek seferlik, insan gözetimli annotasyon koşusu. |

## Katalog ve hiyerarşi

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Kayıt uzayı | 106.183 parent + 125.108 subunit = 231.291 kayıt. Kaynak: YÖK + ROR-TR alias'ları. | ROR — küresel, ~110k+ kayıt. Yalnızca ROR ID'si olan kurumlar işleniyor; ROR'suz kurum yapısal olarak dışlanmış. |
| Hiyerarşi modeli | İki seviyeli, açık: parent (üniversite/hastane/bakanlık) → subunit (fakülte/bölüm). Sorgu 3 seviyeli gelebiliyor, seviye eşleme kurala değil aramaya bırakılıyor. | Düz liste. ROR'da fakülte/bölüm seviyesi modellenmiyor — departman bilgisi affiliation string'inden atılıyor, yalnızca kurum kalıyor. |

## Mimari

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Boru hattı aşamaları | `normalize → decompose → resolve → gate → judge → decide` — 6 ayrı, birbirine sızmayan paket. | `[parser]` `veri çekme → model eğitimi (NN + HF, paralel) → gold test → API deploy` — klasik ML pipeline'ı, Databricks/Spark. `[gold]` `lookup tool → (gerekirse) web_search → JSON annotasyon` — tek turlu ajan döngüsü. |
| Aday üretimi | Elasticsearch, iki kanal: BM25 + kNN (vektör), birleştirilip hakeme sunuluyor. Parent havuzunun %16,2'si yalnızca vektör kanalından geliyor. decompose çoklu-hipotez üretip msearch ile sorguluyor. | `[parser]` Retrieval yok — model uçtan uca tahmin üretiyor (klasik sınıflandırma), aday havuzu kavramı yok. `[gold]` Normalize edilmiş isim → ROR TSV üzerinde exact-match sözlük araması. Fuzzy/vektör yok. |

## Karar katmanı

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Triyaj / karar mekanizması | Önce LLM'siz deterministik gate (exact-omurga kuralı, bm25/kosinüs skoru karara girmiyor) kolay vakaları ayırır; kalanlar LLM hakeme gider. | `[parser]` Eğitilmiş modelin olasılık çıktısı — eşik tabanlı, deterministik kural katmanı yok. `[gold]` Karar tamamen LLM'de: tool-use ile lookup + gerekirse web arama, sonucu doğrudan JSON'a yazıyor. |
| LLM kullanımı | Yerel Gemma 4 (E4B), Ollama üzerinde. Maliyet gerekçesiyle bulut/Claude API kullanılmıyor — kapalı devre. | `[gold]` Bulut Claude API (varsayılan Opus 4.5), token + web_search maliyeti canlı izleniyor, istek başına $ raporlanıyor. `[parser]` LLM yok — ince ayarlı HuggingFace dil modeli + ayrı basit sinir ağı, klasik denetimli eğitim. |

## Çıktı ve hata felsefesi

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Etiket şeması | `auto_match` / `review` / `ambiguous` / `no_match` — dört etiket, ikisi insan kuyruğuna düşüyor. | `[gold]` `high` / `medium` / `low` güven + boş `ror_id` ve serbest metin not. `[parser]` Ham olasılık skoru + ROR id listesi — ayrı bir etiket şeması yok. |
| "Bulunamadı" felsefesi | `no_match` birinci sınıf bir cevap. `auto_match` hedef kesinlik ≥%98 — maliyet asimetrisi net: yanlış eşleşme, hiç cevap vermemekten daha pahalı. | `[gold]` Aynı ilke, kod seviyesinde zorunlu: *"never invent or guess ROR IDs"* — sistem promptunda açık kural. `[parser]` ROR'u olmayan kurum eğitim setinden zaten çıkarılmış; "bulunamadı" ayrı bir durum olarak modellenmemiş. |
| Çok kurumlu / iç içe ifade | Bilinen defekt: tek kayıtta birden fazla kurum karışıyor. Ölçüldü, çözüm ertelendi. | İkisinde de tasarımın parçası: tek affiliation string'inden birden fazla ROR id üretilebiliyor; `"Center X, University Y"` gibi ifadelerde ikisi de ayrı kurum sayılıyor. |

## Normalizasyon ve dil

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Ad normalizasyonu | Türkçe-doğru küçük harf (I/İ ayrımı), görünmez karakter temizliği, kısaltma genişletme. Kural yazmak yerine olası tüm bölünmeler Elasticsearch'e soruluyor. | `[gold]` Unicode NFD ile aksan/diakritik temizleme (é→e, ü→u), lowercase, boşluk sıkıştırma — tek geçişlik, kurala dayalı fonksiyon. |
| Dil kapsamı | TR↔EN ikiliği açık bir tasarım sorunu: aynı kurum iki dilde neredeyse hiç karakter örtüşmüyor, alias listesiyle köprüleniyor. YÖK için 1.846 sorgu elle incelendi, 1.195 düzeltme — token kuralı değil kapalı-küme bilgisi işe yaradı. | Küresel çok dilli; ROR'un kendi alias/etiket listeleriyle örtük çözülüyor. Türkçeye özel bir katman yok. |
| Şirket / kurumsal ad işleme | Yok — katalog TR akademik/sağlık/devlet ağırlıklı, şirket son eki mantığı gerekmiyor. | `[gold]` Var: son ek temizleme (`Inc./Ltd./GmbH/S.A./B.V./K.K.`…) + ülke-farkında ikinci deneme (`"IBM (United States)"`). 3 kademeli fallback. |

## Doğrulama ve altyapı

| Boyut | Bizim Sistem (v3) | OpenAlex |
|---|---|---|
| Test / gold set | `benchmark_500_sample.csv` (500 sorgu, 39 gold no_match). Ayrı bir gold set denemesi reddedildi — 7 müdahalenin 6'sı başabaş çıktı, ölçüm tavanına çarpıldı. | `[parser]` 1000 "kolay" + 500 "zor" + CWTS küratörlüğünde çok-kurumlu set + 200 rastgele — katmanlı zorluk seviyeleri. `[gold]` Kendisi bir gold set üretim hattı — henüz sabit bir set değil, canlı annotasyon çıktısı. |
| Altyapı | Docker + Elasticsearch + Ollama; iç kullanım API'si. | `[parser]` Databricks/PySpark eğitim → yerel veya AWS'de `model_to_api` deploy. `[gold]` Yerel script, eşzamanlılık + rate-limit farkındalığı ile toplu iş; idempotent devam (kaldığı satırdan sürüyor). |
| Ölçek | Envanter hedefi ~438.000 satır; katalog 231.291 kayıt. | OpenAlex API canlıda 250M+ eser üzerinde sürekli çalışıyor; ROR ~110k+ kayıt. |

---

## Sentez

**Ortak zemin — ikisi de "uydurmayı" kod seviyesinde yasaklıyor.**
Bizim %98 auto_match hedefi ve no_match'in birinci sınıf sayılması, OpenAlex gold-standard'ın sistem promptundaki *"never invent or guess ROR IDs"* kuralıyla aynı maliyet asimetrisini kabul ediyor: yanlış cevap, cevapsızlıktan daha pahalı.

**Gerçek ayrışma — retrieval+seçim mi, uçtan uca sınıflandırma mı.**
Biz Elasticsearch'ten aday havuzu çıkarıp hakeme seçtiriyoruz; OpenAlex'in üretim sistemi retrieval'i tamamen atlayıp modeli doğrudan tahmine zorluyor. Gold-standard aracı ise üçüncü bir yol: exact-match sözlük + ajan tool-use.

**Taşınabilir ders — şirket adı işleme ve iç içe kurum çıkarımı.**
gold-standard'ın 3 kademeli kurumsal-ad fallback'ı ve "iç içe ifadede ikisini de ayrı kurum say" kuralı, bizim ertelenmiş çok-kurumlu defekt için doğrudan uygulanabilir bir referans tasarım sunuyor.

---

## Not

`institution_resolver_v4` adıyla OpenAlex yaklaşımlarından birini (exact-match+tool-use ya da eğitilmiş sınıflandırıcı) kendi parent+alias verimizle deneme fikri gündeme geldi, ancak **denenmedi** — kapsam netleştirilmeden vazgeçildi (2026-08-26).
