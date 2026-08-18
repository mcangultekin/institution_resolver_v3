# LLM hakem katmanı — prompt/şema deneyleri

*13-14 Ağustos 2026, tek oturum. 7 varyant × 100 sorgu = 700 LLM çağrısı,
`gemma4:e4b` (native Ollama, Metal GPU), ES `institutions_v1`.*

> **Bu rapor kendi kendine yeterli olacak şekilde yazıldı.** Deney kodu ve ham
> çıktı CSV'leri kullanıcı kararıyla oturum sonunda SİLİNDİ (repo deneysel
> değişiklik taşımasın diye) — aşağıdaki sayılar ve vaka listeleri, o verinin
> kalan tek kaydıdır. Hiçbir değişiklik commit EDİLMEDİ.

---

## 0. Özet

| Sonuç | Karar |
|---|---|
| **Bağlı şema** (subunit ⊂ seçilen parent) | **KABUL** — ama tek başına yeterli değil |
| Kosinüsün hakeme gösterilmesi (3 farklı biçimde) | **RED** |
| Tür tutarlılığı kuralı (prompt) | **RED** — kazancı var ama net negatif |
| Ayırt edici kelime kuralı (prompt) | **RED** — ters tepti |
| Aday listelerinden sonra kontrol listesi | **KISMİ** — kural hasarını azaltır, tek başına kazanç değil |

**En önemli bulgu:** başlangıçtaki iki şikâyetin kökü hakemde değil, **aday
üretiminde (retrieval)**. Ölçülen hataların büyük kısmında doğru kayıt aday
havuzunda hiç yok; hakemden içinde doğru cevabın bulunmadığı bir listeden seçim
yapması isteniyor. Hiçbir prompt kuralı bunu düzeltemez.

**İkinci bulgu:** prompt'a "şunu yapma" kuralı eklemek bu modelde **geri
tepiyor**. Ölçüldü: +333 token kural → `auto_match` %69→%73, `review` %3→%1.
Temkin artsın diye eklenen kurallar modeli daha kararlı yaptı.

---

## 1. Başlangıç: iki şikâyet ve büyüklükleri

1. `Avcılar Anadolu Lisesi` → `Anadolu Üniversitesi` tipi tür-atlamalı eşleşmeler
2. "Kurum-birim uyuşmazlığı" hatasının çokluğu — *"bunu seçebiliyor olmaması lazım"*

Önceki üretim koşusundan (`kaggle_judge_sonuc.csv`, 3.000 satır, envanter modu)
ölçülen büyüklükler:

| | satır | pay |
|---|---:|---:|
| `status=error` toplam | 243 | %8,1 |
| — bunun **kurum/birim uyuşmazlığı** olanı | **232** | **%7,7** |
| — biçim hatası | 11 | %0,4 |
| `auto_match` içinde lise/ortaokul → üniversite | 6 | — |

Uyuşmazlık hatası **tüm sorguyu düşürüyordu**: parent kararı doğru olsa bile
`JudgeValidationError` fırlatılıyor, satır çöpe gidiyordu.

Tür hatası örnekleri (hepsi `auto_match`, yani sessizce dışarı çıkmış):

```
Ordu Fen Lisesi                   -> ORDU ÜNİVERSİTESİ
Kastamonu Fen Lisesi              -> KASTAMONU ÜNİVERSİTESİ
Bahçeşehir Koleji                 -> BAHÇEŞEHİR ÜNİVERSİTESİ
Mehmet Akif Ersoy Ortaokulu       -> BURDUR MEHMET AKİF ERSOY ÜNİVERSİTESİ
İZMİT NAMIK KEMAL ANADOLU LİSESİ  -> TEKİRDAĞ NAMIK KEMAL ÜNİVERSİTESİ
```

Dikkat: bu beşinde ayırt edici kelime **ortak** (Ordu, Kastamonu, Bahçeşehir,
Namık Kemal). Yani "jenerik token" açıklaması bunları kapsamıyor — farklı olan
tek şey kurum türü.

---

## 2. Kök neden analizi (prompt'un kural kural incelenmesi)

Prompt'un 11 karar kuralı tek tek incelendi. Üç sınıf çıktı:

**(a) Ölü kurallar — şema zaten fiziksel olarak zorluyor.** Ollama'nın kısıtlı
üretimi (llama.cpp GBNF grameri) şu dört kuralı üretim aşamasında imkânsız
kılıyor; prompt'taki metinleri yer kaplamaktan başka iş yapmıyor:

| Prompt kuralı | Şemadaki karşılığı |
|---|---|
| "listeler arası id GEÇERSİZDİR" | `parent.matched_id.enum` = yalnız parent adayları |
| "yeni id/ad UYDURMA" | aynı enum — başka dizge üretilemez |
| "no_match'te matched_id null" | `no_match` dalı: `const`+`null`; diğer dal no_match'i dışlıyor |
| verdict değer listesi | `enum` |

**(b) Çelişkili kural.** `KARAR KURALLARI`nın ilk maddesi:

> *"Kurum (parent) ve alt-birim (subunit) kararını AYRI ayrı ver — biri
> diğerini otomatik belirlemez."*

Buna karşılık `judge._validate_ids`, subunit'in gerçek `parent_id`'si seçilen
parent'tan farklıysa cevabı **reddediyordu**. Yani modele "bağımsız karar ver"
denip, bağımsız karar verdiği için cezalandırılıyordu. **232 satırlık hatanın
kaynağı bu çelişki.**

**(c) Eksik kurallar.** Ülke/şehir için "ZORUNLU kontrol" var; **kurum türü için
hiçbir şey yok**. Ayrıca parent adaylarında tür bilgisi hakeme hiç gösterilmiyor.

---

## 3. Yöntem

**Varyant mekanizması.** `PromptVariant` bayrakları + `VARIANTS` kaydı; her
deneysel fikir bağımsız bir bayrak. `v1` (mevcut prompt) çıktısı **birebir**
korundu ve regresyon testiyle kilitlendi — tüm karşılaştırmaların tabanı.

**Örneklem — 100 sorgu, tabakalı.** Kaynak: yukarıdaki 3.000 satırlık koşu.
Düz rastgele örneklemede nadir hata sınıfları (tür hatası 6/3000 = %0,2) hiç
düşmezdi; orantılı paylar korunup hata sınıfları ×2,5 takviye edildi, her satıra
ağırlık yazıldı (havuz payı / örneklem payı) ki takviye sonucu çarpıtmasın.

| Sınıf | Havuz | Pay | Kota | Ağırlık |
|---|---:|---:|---:|---:|
| auto_match | 1.895 | %63,2 | 51 | 1,24 |
| no_match | 696 | %23,2 | 21 | 1,11 |
| uyuşmazlık hatası | 232 | %7,7 | 17 | 0,46 |
| belirsiz (review/ambiguous) | 160 | %5,3 | 5 | 1,07 |
| diğer hata | 11 | %0,4 | 3 | 0,12 |
| tür hatası | 6 | %0,2 | 3 | 0,07 |

**Kontrollü koşu.** Yedi varyantın tamamı **aynı oturumda**, aynı 100 sorguda,
aynı ayarlarla (`--cosine` dahil) koşuldu. Kaggle CSV'si taban olarak
KULLANILMADI — farklı gün, farklı ortam ve farklı boru hattı (envanter modu:
gate+hakem; buradaki koşular: düz `resolve→judge`). Ondan yalnızca *hangi
sorguların* koşulacağı alındı.

---

## 4. Varyantlar

| Varyant | Bağlı şema | Kosinüs | Tür+ayırt edici kuralı | Son kontrol listesi |
|---|:---:|:---:|:---:|:---:|
| v1 (taban) | — | — | — | — |
| v2-cos | — | ham | — | — |
| v3-cos-not | — | ham + okuma notu | — | — |
| v4-bagli | ✓ | — | — | — |
| v5-bagli-cos | ✓ | ham + not | — | — |
| v6-kurallar | ✓ | — | ✓ | — |
| v7-kontrol | ✓ | — | ✓ | ✓ |

---

## 5. Sonuçlar

### 5.1 Karar dağılımı

| Varyant | auto_match | review | ambiguous | no_match | HATA |
|---|---:|---:|---:|---:|---:|
| v1 | 57 | 2 | 4 | 20 | **17** |
| v2-cos | — | — | — | — | 18 |
| v3-cos-not | — | — | — | — | 13 |
| **v4-bagli** | 69 | 3 | 3 | 25 | **0** |
| v5-bagli-cos | — | — | — | — | 0 |
| v6-kurallar | 73 | 1 | 4 | 22 | 0 |
| v7-kontrol | 70 | 4 | 2 | 24 | 0 |

> **"Hata sayısı" bu iş için yanıltıcı bir metriktir.** v6'da hata 0'dır ama
> kararların kalitesi v4'ten düşüktür: uyuşmazlık hatası kapandığı için sayaç
> sıfır görünür, yanlışlar sessizce `auto_match` içine dağılır. Her
> karşılaştırmada değişen kararlar **tek tek gözle** incelendi.

### 5.2 Kosinüs — RED

Üç ayrı yapıda ölçüldü, hiçbirinde net kazanç vermedi:

| Karşılaştırma | Sonuç |
|---|---|
| v1 → v2 (ham kosinüs) | **net zarar**: 17→18 hata; uyuşmazlıkta 4 düzelme / 5 bozulma |
| v1 → v3 (kosinüs + not) | karışık: 13 hata ama 4 yeni sahte güven |
| v4 → v5 (bağlı şema üstünde) | **başabaş**: 7 iyi / 8 kötü |

**Kararı verdiren şey sayı değil, tekrarlanabilirlik.** Şu dört hata kosinüs
gösterilen **her** varyantta birebir çıktı (v2, v3, v5):

```
Van YYÜ                      -> De Lijn (Belgium)
Türk Standartları Enstitüsü  -> Swedish Standards Institute
Sakarya Büyükşehir Belediyesi-> Ordu Büyükşehir Belediyesi
Atatürk Sanatoryum T&R Hosp. -> Gülhane Eğitim ve Araştırma Hastanesi
```

Üçü de ülke/şehir çelişkisi — ve prompt'ta bunu yasaklayan "ZORUNLU kontrol"
kuralı zaten var. Kosinüs, mevcut bir kuralı ezecek kadar güçlü bir "kanıt"
gibi okunuyor.

Bu, 27 Temmuz 2026'daki N=8 ölçümünün (e5-base anizotropik; alakasız çiftler
μ=0,837; doğru eşleşme havuz-içi kosinüs sıralamasında ort. 4.) 300 sorgu ile
teyididir. **Kosinüs kNN retrieval'da kalmalı** — çapraz-dilli recall'daki
değeri ayrı ve kanıtlı; yalnızca hakeme GÖSTERİLMEMELİ.

### 5.3 Bağlı şema (v4) — KABUL, koşullu

Uyuşmazlık hatası **şema seviyesinde imkânsız** hale getirildi: üst seviyede
`anyOf`, her parent seçeneği için bir dal, o dalda subunit enum'u yalnız o
parent'a bağlı adayları içeriyor. (llama.cpp iç içe `anyOf`+`const` grameri
sorunsuz derledi — bu bir risktti, doğrulandı.)

**Sonuç: 17 hata → 0.** Uyuşmazlıkta 14 düzelme, 0 bozulma.

**Ama fatura var.** 14 uyuşmazlık hatasının 10'u `auto_match`'e döndü ve
bunların yalnız 1'i doğruydu:

```
zeynep kamil                            -> Zeynep Kamil Hospital          DOĞRU
Nevşehir ... Bilim ve Sanat Merkezi     -> Roketsan
Dr. Suat Seren Göğüs Hastalıkları EAH   -> Decision Research
Türk Hava Yolları                       -> Turkish Air Force Academy
İSTANBUL MEHMET AKİF ERSOY GÖĞÜS KVC    -> BURDUR MEHMET AKİF ERSOY ÜNİVERSİTESİ
Düzce Bilim ve Sanat Merkezi            -> AZERBAYCAN DEVLET ... SANAT ÜNİ.
Northern Arizona University             -> Museum Of Northern Arizona
İLAHİYAT PR.                            -> Azərbaycan İlahiyyat İnstitutu
İktisadi ve İdari Bilimler Fak. ... UİB -> International Relations Council of Turkey
Gıda ve Yem Kontrol Merkez Arş. Enst.   -> Plant Protection Central Research Institute
```

**Yorum:** uyuşmazlık hatası yalnız bir defekt değil, aynı zamanda bir *kafa
karışıklığı dedektörü*ydü. Model tutarsız bir parent/subunit çifti seçtiğinde
bu "ne yaptığımı bilmiyorum" sinyaliydi ve tüm cevap reddediliyordu.
Tutarsızlık ifade edilemez kılınınca, model kafası karışıkken **tutarlı ama
yanlış** bir şey seçiyor ve güvenle söylüyor. Gürültülü arıza, sessiz yanlışa
dönüştü — prompt'un kendi ölçütüyle daha pahalı:

> *"Alakasız bir kayda auto_match vermek, hiç cevap verememekten ÇOK daha
> pahalı bir hatadır."*

Kabaca: 24 değişiklikte ~9 iyi, ~11 kötü, ~4 nötr.

### 5.4 Tür + ayırt edici kelime kuralları (v6) — RED

v4 → v6: 16 değişiklik, ~4 iyi / ~10 kötü. **v6, v4'ten kötü.**

Düzelenler (tür kuralı çalıştığında gerçekten çalışıyor):

```
Northern Arizona University    Museum Of Northern Arizona  -> no_match
UÇUCU SAĞLIĞI ARŞ. MERKEZİ     SAĞLIK BİLİMLERİ ÜNİ.       -> no_match
Yağlı Tohumlar Arş. Enst.      Black Sea Agricultural R.I. -> no_match
İktisadi ve İdari Bilimler F.  Int. Relations Council      -> no_match
```

Bozulanlar — ve kalıba dikkat:

```
Manavgat Devlet Hastanesi       no_match -> Serik Devlet Hastanesi
Sakarya Büyükşehir Belediyesi   no_match -> Başakşehir Belediyesi
Muğla EAH Obstetrics            review   -> Ağrı EAH (auto_match)
Atatürk Sanatoryum T&R Hosp.    no_match -> Near and Far Aid
KAHRAMANMARAŞ HEALTH ACADEMY    no_match -> Laser & Health Academy
Türk Standartları Enstitüsü     no_match -> Swedish Standards Institute
Van YYÜ                         no_match -> De Lijn (Belgium)
Diyarbakır Ağız ve Diş S.H.     no_match -> Gazi Hastanesi
```

**İlk üçü, ayırt edici kelime kuralının tam olarak yasakladığı hata.** v4'te
üçü de doğruydu; kural eklenince bozuldular. Kuralın metninde karşı-örnek olarak
şu kullanılmıştı:

> *"Aynı şekilde 'X Devlet Hastanesi' ile 'Y Devlet Hastanesi'..."*

**Hipotez (doğrulanmadı, doğrulanmaya değer): yasaklamak için verilen olumsuz
örnek, yasakladığı davranışı hazırlıyor (priming).** v7'de aynı sınıftan
dördüncü bir vaka daha çıktı (`Afyonkarahisar → Sivas State Hospital`), yani
kalıp tek koşuya özgü değil.

**Ölçülen davranış kayması:** prompt 2.464 → 2.797 token (+%13); `auto_match`
%69→%73, `review` %3→%1. Temkin için eklenen kurallar modeli daha kararlı yaptı.

### 5.5 Son kontrol listesi (v7) — kısmi fayda, net kazanç değil

Madde 6 planı "reddetme kurallarını aday listelerinden sonraya taşı"ydı. **Tam
metin taşınmadı**, çünkü prompt bilerek "sabit blok başta, değişken veri sonda"
kurulu (Ollama ortak PREFIX'i KV-cache'ler; LLM süresinin %85'i prompt işleme).
Kuralları sona taşımak onları önekten çıkarır, her çağrıda yeniden işlenirler.
Bunun yerine sona ~70 token'lık kısa bir kontrol listesi (tür / yer / ayırt
edici) konuldu; tam metin başta kaldı.

- **v6 → v7:** 11 değişiklik, ~6 iyi / ~4 kötü. Kontrol listesi v6'nın aşırı
  kararlılığını geri çekti (dağılım v4 profiline döndü).
- **v4 → v7:** 17 değişiklik, ~7 iyi / ~9 kötü. **v7, sade v4'ü geçmiyor.**

Yani kontrol listesi kural hasarını azaltıyor ama kuralların kendisi net
negatif olduğu için toplam yine v4'ün altında kalıyor.

---

## 6. Asıl teşhis: sorun retrieval'da

Bozulan vakaların aday havuzları incelendi. Örüntü net.

**`Manavgat Devlet Hastanesi`** (katalogda YOK — doğrulandı; yalnız Manavgat'taki
fakülteler var, hastane yok). Havuz:

```
Sivas State Hospital        Sivas     tsr=84
Denizli Devlet Hastanesi    Denizli   tsr=80
Ermenek Devlet Hastanesi    Karaman   tsr=80
Şarkışla Devlet Hastanesi   Sivas     tsr=78
Suluova Devlet Hastanesi    Suluova   tsr=80
Serik Devlet Hastanesi      Antalya   tsr=84
Igdir State Hospital        Iğdır     tsr=84
Seyhan Devlet Hastanesi     Adana     tsr=82
```

Sekiz aday, hepsi başka şehrin devlet hastanesi, hiçbiri doğru değil, benzerlik
skorları 78-84'te sıkışmış. Jenerik kısım ("Devlet Hastanesi") skoru domine
ediyor; ayırt edici olan şehir adı skora neredeyse hiç girmiyor.

**`Sakarya Büyükşehir Belediyesi`** — Sakarya'nınki havuzda yok, ve **en yüksek
skoru yanlış olanlar alıyor**:

```
Ordu Büyükşehir Belediyesi              tsr=89   <- en yüksek
Bursa Metropolitan Municipality         tsr=88
Metropolitan Municipality of Kocaeli    tsr=84
Başakşehir Belediyesi                   tsr=72
```

**`Van YYÜ`** — akronim hiçbir kanaldan çözülmüyor, havuz tamamen alakasız:

```
De Lijn (Belgium)                       BE  tsr=14   <- listenin BAŞI
Văn phòng ban chỉ đạo 33                VN  tsr=19
Vanboeijen                              NL  tsr=35
Court of Justice of the European Union  LU  tsr=60
Van Lang University                     VN  tsr=60
Yerevan State University                AM  tsr=40
```

`De Lijn`'in her kosinüs varyantında ısrarla seçilmesinin sebebi: **listenin ilk
sırasında.** Küçük modelin pozisyon yanlılığı bu kod tabanında zaten belgeli
(`judge/candidates.py`, "Ege" bulgusu).

**Sonuç:** bu vakalarda hakem yanlış karar vermiyor — önüne doğru cevabın
bulunmadığı bir liste konuyor. Verebileceği tek doğru cevap `no_match`, ve v4
bunu veriyordu; kural eklemek onu bundan caydırdı.

**Ek bulgu:** katalog ROR tabanlı ve şirketleri de içeriyor (`Battery Ventures`,
`CSX`, `Roketsan`, `De Lijn`). Bu yüzden `Bilim ve Sanat Merkezi` sorgusu bir
savunma sanayii şirketiyle eşleşebiliyor. Aynı sebeple katalogda liseler de var
(`Eskişehir Anadolu Lisesi`) ve hastaneler de (`Zeynep Kamil Hospital`) — yani
"lise/hastane ⇒ no_match" gibi bir kısayol YANLIŞ olur.

**Veri kısıtı:** parent kayıtlarında **tür alanı yok** — ne ES'te ne ham CSV'de.
Alanlar: `id, name, normalized_name, country, city, canonical_ref,
active_override` (+aliases). Tür kuralı bu yüzden ad-tabanlı olmak zorunda kaldı.

---

## 7. Öneriler (uygulanmadı — sonraki oturum için)

### Öneri 1 — Ayırt edici kelime kapsamını KODDA hesapla *(en yüksek getiri)*

Prompt kuralı olarak denendi ve geri tepti. Aynı bilgi deterministik olarak
hesaplanabilir. "Ayırt edici" = düşük doküman frekansı: `hastanesi` on binlerce
kayıtta, `manavgat` bir avuçta geçer.

- **Altyapı yok:** projede df/idf hesabı bulunmuyor (yalnız rapidfuzz). `build-data`
  adımında bir token→df haritası üretilmeli (`data/processed/token_df.json`).
- **Sinyal:** `ScoredCandidate`'a `distinctive_covered: bool` +
  `missing_distinctive: list[str]` — `exact_match`/`exact_match_text` ikilisiyle
  aynı desen.
- **İki kullanım:** (a) hakeme sert sinyal olarak göster, (b) hiçbir aday ayırt
  edici token'ı karşılamıyorsa **hakemi hiç çağırmadan** `no_match`. Ölçüm (b)'yi
  destekliyor — model bu tür sinyallere güvenilmez tepki veriyor. Yan fayda: o
  sorgular ~25 sn yerine ~1 sn'de biter.
- **Risk:** eşik ayarı; doğru eşleşmeleri elemek. Kontrol grubu (51 `auto_match`)
  bozulmamalı.
- **Türkçe:** çekim eki sorunu (`Manavgat` / `Manavgat'ta`) — `normalize/query_pipeline.py`
  üzerinden geçirilmeli.
- **Yeniden indeksleme GEREKMEZ.** Gate dalga planındaki **G2 (df)** maddesiyle aynı iş.

### Öneri 2 — Akronim genişletme

`Van YYÜ` havuzu %14 benzerlikli çöp döndürüyor. `normalize/abbreviations.py`
var ama içeriği `BÖL. → BÖLÜMÜ`, `PR. → PROGRAMI` tipi yapısal kısaltmalar;
kurum akronimleri (`YYÜ`, `ODTÜ`) kapsam dışı ve modül riskli kısaltmaları
bilerek dışlıyor.

Katalogdan türetme önerilir (baş harflerden akronim üret → alias ekle), elle
sözlükten daha sürdürülebilir. **Asıl risk çakışma:** üretilen akronim tek bir
kuruma denk gelmiyorsa alias sayılmamalı.

**Emek yüksek:** `ingest/` değişikliği + ~450k kaydın yeniden indekslenmesi.
Ölçümü için akronim ağırlıklı ayrı bir örneklem gerekir.

### Öneri 3 — Havuz kalitesi eşiği

Hiçbir aday belirli bir eşiği geçmiyorsa (Van YYÜ'de en iyisi %14) sorgu hakeme
gitmesin ya da bu bilgi hakeme verilsin. Öneri 1(b) bunun büyük kısmını zaten
kapsar; ayrı değeri, ayırt edici token'ın kendisinin tanınamadığı vakalar için
ucuz bir emniyet ağı olması. **Emek düşük.**

### Ölçülmemiş kalan iki fikir

- **Ölü kuralları prompt'tan silmek** (§2a): ~400 token siler. Şema zaten
  zorladığı için davranışı değiştirmemesi *beklenir* — ama v6 ölçümü token
  eklemenin zarar verdiğini gösterdi, dolayısıyla token çıkarmanın **fayda**
  vermesi muhtemel. Test edilebilir hipotez.
- **`TAM_EŞLEŞME NOTU`nu kısaltmak**: 11 satır, içinde istisna-içinde-istisna
  var; aynı işi `unit_phrase`'in şemadaki sıra kilidi zaten mekanik olarak
  yapıyor.

### Önerilen sıra

`Öneri 1(b)` → `Öneri 3` → ölç → `Öneri 2`

Üçü de hakemi değil **retrieval'ı** düzeltir. Bu doğru yön, ama not: bu oturumun
tüm ölçüm altyapısı prompt A/B'si için kuruldu; retrieval değişikliğini ölçmek
için havuzun kendisine bakmak gerekir, yalnızca nihai karara değil.

---

## 8. Ölçümün kısıtları (dürüstlük notu)

1. **Gold etiketli referans set YOK.** "Doğru/yanlış" yargıları bu raporu yazana
   ait; dayanak sorgu metni, seçilen kaydın adı/ülkesi ve aday havuzunun tamamı.
   Sayılar (~9 iyi / ~11 kötü) bu yüzden **kesin değil, yönü gösterir**.
2. **100 sorgu küçük.** Yalnızca belirgin etkiler görünür; küçük etkiler gürültüye
   karışır. Buna karşılık kosinüsün dört imza hatası üç bağımsız koşuda birebir
   tekrarlandı — o bulgu sağlam.
3. **"Hata sayısı" yanıltıcı metrik** (§5.1 kutusu).
4. **Hakem oturum içinde deterministik değil.** Bu yüzden yedi varyantın tamamı
   aynı oturumda koşuldu; farklı günlerin çıktıları kıyaslanmadı.
5. **Örneklem hata-takviyeli.** Ham sayılar örneklemi anlatır; havuza genelleme
   için ağırlık kullanılmalı (§3 tablosu).
6. **Tür hatası tabakası yalnız 3 satır.** O sınıfa dair sonuçlar gösterge
   niteliğinde, ölçüm değil.

---

## 9. Nihai tavsiye

**Bağlı şema (v4) tek gerçek kazanç** — yapısal bir defekti kapatıyor, %7,7'lik
tam kayıp sınıfını sıfırlıyor. Ama **tek başına canlıya alınmamalı**: açtığı
sessiz-yanlış deliği, kapattığı gürültülü arızadan daha pahalı olabilir.

O delik **prompt kuralıyla kapanmıyor** — iki kural yazıldı, ölçüldü, ikisi de
net negatif çıktı. Kapanacağı yer retrieval: Öneri 1.

**Kosinüs kapatılmalı.** Üç yapıda ölçüldü, arıza kalıbı tekrarlanabilir.
kNN retrieval'daki yeri korunur.
