# Institution Resolver v3 — Proje Raporu

*Serbest metin kurum ifadelerini kanonik katalog kayıtlarına çözen sistem.*

---

## 1. Problem ve kapsam

### 1.1 Çözülen iş

Akademik yayın verisinde kurum bilgisi (*affiliation*) serbest metin olarak gelir:

```
"Gazi Üniversitesi Mühendislik Fakültesi Makine Mühendisliği Bölümü"
"Department of Physics, Middle East Technical University, Ankara, Turkey"
"T.C. Sağlık Bakanlığı, Adana Fatma Kemal Timuçin Ağız ve Diş Sağlığı Merkezi"
```

Bu ifadelerin her birinin, kurum kataloğumuzdaki **hangi kayda** karşılık geldiğini
bulmamız gerekiyor. Katalog iki seviyeli:

| seviye | ne | adet |
|---|---|---:|
| **parent** | ana kurum (üniversite, hastane, bakanlık, şirket) | 106.183 |
| **subunit** | ona bağlı birim (fakülte, bölüm, anabilim dalı) | 125.108 |
| | **toplam** | **231.291** |

İşlenecek gerçek veri hacmi **~438.000 satır**.

### 1.2 Neden basit bir arama yetmiyor

Bu, "metni ara, en benzerini seç" ile çözülebilecek bir problem değil. Gerçek veriden
çıkan, her biri ölçülmüş dört zorluk sınıfı var:

**a) Aynı adlı, farklı ülkedeki kurumlar.** Katalog küresel (ROR kaynaklı yabancı
kayıtlar dahil). `"University of Health Sciences"` sorgusu üç ayrı gerçek kayda
birebir uyuyor: Somali (Bosaso), Kamboçya (Phnom Penh) ve Türkiye'deki *Sağlık
Bilimleri Üniversitesi* — sonuncusunun İngilizce adı tam olarak budur. Salt metin
benzerliği bu üçünü ayıramaz.

**b) Dil ikiliği.** Katalog adı Türkçe, sorgu İngilizce (ya da tersi) olabiliyor:
`"Ege University Medical Faculty"` ile `EGE ÜNİVERSİTESİ` kayıtları karakter
düzeyinde neredeyse hiç örtüşmez. Doğru eşleşme ancak kaydın alias (diğer ad)
listesi üzerinden kurulabiliyor.

**c) Seviye uyuşmazlığı.** Sorgu üç seviyeli olabiliyor (Üniversite › Fakülte ›
Bölüm), katalog iki seviyeli. Aradaki seviyenin hangi tarafa yazılacağı sabit bir
kuralla belirlenemiyor.

**d) Kurum sınırının belirsizliği.** `"University of Oxford"` gibi adlarda işaretçi
kelime kurumun adını *başlatıyor*, bitirmiyor. Katalogdaki 106.183 parent kaydının
**~%8'i** (8.566 kayıt) bu ters-örüntüde. Ayrıca `"Eskişehir Osmangazi Üniversitesi
Tıp Fakültesi Hastanesi"` gibi, zincirleme birden fazla işaretçi içeren tek bir
kurum adı da var.

### 1.3 Kapsam dışı

Kurum adı **çıkarımı** (uzun metinden affiliation bulma), yazar eşleştirme ve
katalog bakımı bu sistemin işi değil. Sistem, kendisine verilen kurum ifadesini
çözer.

---

## 2. Çıktı sözleşmesi

Her sorgu için tek bir JSON: **parent** ve **subunit** kararı, her biri bir karar
etiketi + eşleşen kayıt kimliği ile.

| etiket | anlamı | operasyonel karşılığı |
|---|---|---|
| `auto_match` | tek net aday | insan görmez, doğrudan kullanılır |
| `review` | doğru görünüyor ama teyit gerek | insan kuyruğuna düşer |
| `ambiguous` | birden fazla makul aday | insan kuyruğuna düşer |
| `no_match` | katalogda karşılığı yok | insan kuyruğuna düşer |

**`no_match` birinci sınıf bir cevaptır.** Sistem "en benzerini" seçmeye zorlanmaz.
Bunun gerekçesi maliyet asimetrisi: alakasız bir kayda `auto_match` vermek, hiç
cevap verememekten çok daha pahalı bir hatadır — çünkü ilki sessizce veriye
karışır, ikincisi kuyrukta görünür. Aynı nedenle `auto_match` için hedeflenen
kesinlik **%98 ve üzeri** olarak belirlenmiştir.

Ayrıca `parent = auto_match` + `subunit = no_match` geçerli ve yaygın bir
sonuçtur: kurum bulunur, sorgudaki birimin katalogda karşılığı yoktur.

---

## 3. Mimari

```
ÇEVRİMDIŞI (bir kez):
  ham CSV ──► kanonikleştirme ──► embedding ──► Elasticsearch
              (kopya birleştirme)  (vektör)      (tek indeks)

SORGU ANI:
  metin ──► normalize ──► aday üretimi ──► triyaj ──► hakem ──► karar
                          (Elasticsearch)  (kural)   (LLM)
```

**Temel ilke: Elasticsearch aday bulur, LLM seçer.** Arama motorundan doğru cevabı
sıralamada 1. yapması beklenmez; görevi doğru cevabı havuza *sokmaktır*. Seçim,
bağlamı değerlendirebilen bir dil modeline bırakılır.

### 3.1 Çevrimdışı akış

Ham CSV kanonik kayda dönüşür: birebir aynı kayıtlar tek kimlik altında
birleştirilir (en büyük klon grubu ~174 özdeş kayıt), her kayıt için arama vektörü
üretilir ve tek bir Elasticsearch indeksine yazılır.

### 3.2 Sorgu anı — katmanlar

| katman | ne yapar | ne yapmaz |
|---|---|---|
| **normalize** | Türkçe-doğru küçük harf (I/İ), görünmez karakter temizliği, kısaltma genişletme | anlam çıkarımı |
| **decompose** | sorgunun hangi bölümünün kurum adı olduğuna dair **hipotezler** üretir | seçim yapmaz |
| **resolve** | her hipotezle arama yapar, adayları birleştirir, her adaya kanıt sinyalleri ekler | karar vermez |
| **gate** | LLM'siz deterministik triyaj: kolayları ve çöpü ayırır | belirsizi çözmez |
| **judge** | kalan sorgular için LLM hakem, adaylar arasından seçer | aday üretmez |
| **decide** | nihai kararı birleştirir | — |

Katmanlar ayrı paketlerdir ve birbirine sızmaz. Bu ayrım, bir katmanı
değiştirdiğimizde diğerlerinin davranışının sabit kalmasını sağlar.

Aday üretimi **iki kanaldan** yapılır: klasik metin araması (BM25) ve anlam
araması (vektör/kNN). İkisi birleştirilir — ölçüldüğünde parent havuzunun
**%16,2'si yalnızca vektör kanalından** geliyor, yani metin araması tek başına
yetmiyor.

---

## 4. Önemli tasarım kararları

**Tek indeks.** Önceki sürümde parent ve subunit ayrı indekslerdeydi; bu, kelime
nadirlik istatistiklerini bozuyordu ("fakültesi" kelimesi parent indeksinde suni
olarak nadir görünüp yanlış kuruma yüksek puan veriyordu). Tek korpus + kayıt tipi
filtresi bu sorunu ortadan kaldırdı.

**Kural yazmak yerine veriye sormak.** Kurum sınırını "şu kelimeden böl" gibi
kurallarla bulmak yerine, sorgunun tüm olası parçaları Elasticsearch'e sorulur ve
hangisi gerçek bir kurum adına oturuyorsa sınır orasıdır. Dil-özel istisna listesi
(İngilizce "of", Almanca "für"...) tutmaya gerek kalmaz.

**Karar değil hipotez.** decompose tek bir sınır seçmez; farklı kurumlara işaret
eden en iyi 5 hipotezi birlikte döndürür. Böylece bu adımdaki bir hata zincirin
sonuna taşınmaz, yalnızca havuza gürültü ekler.

**Recall-güvenli kademelendirme.** Birim araması, tahmin edilen kurumlarla
filtrelenir — ama filtresiz arama da yapılıp sonuçlar birleştirilir. Kurum tahmini
yanlışsa doğru birim kaybolmaz, sadece sırada geriye düşer.

**Yerel LLM, harici API değil.** Hakem katmanında Gemma 4 (E4B) modeli Ollama
üzerinden **yerelde** çalışır. Ticari bir API (Claude, GPT vb.) kullanılmamaktadır;
bu bilinçli bir maliyet kararıdır — sistem yüz binlerce satır işleyecek ve satır
başına API ücreti ölçekte sürdürülebilir değil.

**Modelin uydurması yapısal olarak engellenir.** Hakemin çıktısı bir JSON şemasına
kısıtlanır: seçebileceği kimlikler yalnızca o sorgunun aday listesindeki değerlerdir,
model listede olmayan bir kimliği **fiziksel olarak üretemez**. Buna ek olarak
dönen cevap katalogla karşılaştırılıp doğrulanır (uydurma kimlik, kurum/birim
uyuşmazlığı yakalanır).

---

## 5. Teknoloji ve çalıştırma

| bileşen | seçim |
|---|---|
| arama motoru | Elasticsearch 8.14 (tek indeks, Türkçe + ASCII analizör) |
| anlam vektörü | `multilingual-e5-base` (768 boyut, 231.291 vektör) |
| dil modeli | Gemma 4 E4B, Ollama üzerinden yerel |
| servis | FastAPI (HTTP) + Typer (komut satırı) |
| paketleme | Docker Compose (ES + Ollama + API) |

Kullanım üç biçimde mümkün:

- **Komut satırı** — tekil sorgu (`match` / `gate` / `judge` / `decide`, her biri bir
  sonraki katmanı açar) ve toplu işlem (CSV girdi → CSV çıktı, kaldığı yerden devam
  edebilir).
- **HTTP servisi** — tekil sorgu uçları, toplu iş yükleme, iş durumu takibi ve küçük
  bir demo arayüzü.
- **Colab defteri** — aynı akışın GPU üzerinde çalışan sürümü.

---

## 6. Ölçümler ve kapasite

500 gerçek sorgudan oluşan bir örnek küme üzerinde ölçülen davranış:

| yol | pay | satır başına süre |
|---|---:|---:|
| yalnız kural katmanı (LLM'siz) | %42 | 0,67 s |
| LLM hakeme düşen | %58 | 23,9 s |

**Süre bütçesinin ~%98'i dil modelinde**, modelin içinde de yaklaşık %85'i
*girdi işleme* aşamasında (üretim değil). Ölçülen donanım tavanı: Apple M4,
8 GPU çekirdeği, saniyede ~232 token. Yani sistemin hızını belirleyen tek şey
**modele gönderilen metin uzunluğu**.

**Kapasite tahmini.** Satır başına ortalama ~14 saniye; 438.000 satır için tek
makinede sıralı işlemede kabaca **70 gün**. Bu, projenin en belirgin darboğazıdır
ve iyileştirme çalışmasının odağıdır (bkz. Bölüm 8). Kural katmanının payını
artırmak ve modele giden metni kısaltmak, doğrudan bu süreyi düşüren iki
kaldıraçtır.

---

## 7. Proje geçmişi — denenen ve elenen yaklaşımlar

Sistemin bugünkü hâli, ölçülerek elenmiş bir dizi alternatifin sonucudur. Aşağıdaki
kararların her biri canlı veri üzerinde test edilip kayda geçirilmiştir.

| yaklaşım | sonuç | gerekçe |
|---|---|---|
| Parent/subunit ayrı indekslerde | **elendi** | Kelime nadirlik istatistikleri bozuluyordu |
| Sorguyu işaretçi kelimeden bölme | **elendi** | Kayıtların %8'i ters-örüntüde; dil-özel istisna listesi gerekiyordu |
| Tek sınır kararı | **elendi** | Kısa ve tesadüfi örtüşme, uzun ve doğru parçayı yenebiliyor → çoklu hipoteze geçildi |
| Sınırı birim kanıtıyla doğrulama | **denendi, geri alındı** | 50 sorgulu testte yeni yanlılık ekledi |
| Parent aramasında kanonik ad ile alias'ı ayrı tutma | **elendi** | Ayrım kaldırılınca alias ile arama isabeti %47 → %84,5'e çıktı |
| Daha küçük dil modeli (E2B) | **elendi** | Şüpheli sorgularda körlemesine kesin cevap veriyordu; E4B daha temkinli |
| Hakeme ham benzerlik skoru gösterme | **elendi** | Vektör benzerliği dar bir banda sıkışıyor, alakasız metin bile yüksek puan alıyor — yanıltıcı sinyaldi |
| Hakemden gerekçe metni isteme | **elendi** | Üretilen metin süreyi katlıyordu, karara katkısı yoktu |
| Benzerlik eşiğiyle otomatik eşleştirme | **denendi, çıkarıldı** | Güvenliği daha üst bir katmanın doğruluğuna bağımlıydı |

Bu kayıt bilinçli tutuluyor: aynı fikirlerin ileride yeniden denenmesini önlüyor ve
her tasarım tercihinin arkasındaki ölçümü görünür kılıyor.

---

## 8. Sıradaki işler

1. **Performans.** Süre bütçesi dil modelinde olduğu için iyileştirme oraya
   odaklanıyor: kural katmanının kapsamını genişletmek (LLM'e düşen satır sayısını
   azaltmak) ve modele giden metni kısaltmak. Arama katmanında ölçülmüş, davranışı
   değiştirmeyen iyileştirmeler ayrıca uygulanıyor.
2. **Kural katmanının hassaslaştırılması.** Ülke/şehir tutarlılığı gibi ayırt edici
   sinyallerin kural katmanında da kullanılması — şu an yalnızca dil modeli bu
   kontrolü yapıyor.
3. **Ölçek altyapısı.** GPU'lu ortamda toplu işlem ve paralel çalıştırma
   seçeneklerinin değerlendirilmesi.

---

## Ek A — Terimler

| terim | anlamı |
|---|---|
| **parent / subunit** | ana kurum / ona bağlı birim |
| **alias** | bir kurumun bilinen diğer adları (çeviri, kısaltma, eski ad) |
| **BM25** | klasik metin arama puanlama yöntemi — kelime örtüşmesine bakar |
| **embedding / vektör arama (kNN)** | metni sayı dizisine çevirip *anlamca* yakın kayıtları bulma |
| **normalize** | iki farklı yazılmış aynı ismi tek biçime indirgeme |
| **triyaj (gate)** | LLM çağırmadan, kurallarla kolay/çöp ayırma |
| **hakem (judge)** | adaylar arasından seçimi yapan dil modeli katmanı |
| **recall** | doğru cevabın aday havuzuna girme oranı |

## Ek B — Kaynak düzeni

| yol | içerik |
|---|---|
| `src/institution_resolver_v3/` | paket: `ingest/ normalize/ embedding/ elastic/ retrieve/ gate/ judge/ decide/ eval/ api/ cli/` |
| `config/default.yaml` | tüm ayarlar (her anahtarın yanında hangi ölçüme dayandığı yazılı) |
| `docker/docker-compose.yml` | Elasticsearch + Ollama + API |
| `notebooks/` | Colab akışı |
| `tests/unit/` | 218 birim testi |
| `docs/` | tasarım belgeleri, deney ve ölçüm raporları |
