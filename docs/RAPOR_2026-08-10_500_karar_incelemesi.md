# 500 kararın tek tek incelenmesi — gerçek üretim verisi

*Örneklem: `institution-field-inventory-todo.csv` (301.520 çözülmemiş benzersiz isim)
içinden `seed=42` ile rastgele 500. Koşu: `gate-batch`, `current_institution_name`
sütunu, LLM yok.*

---

## 0. Yöntem ve dürüstlük notu

**Gold etiketli referans set yok.** Aşağıdaki "doğru/yanlış" yargıları bana ait;
dayanağım sorgu metni, seçilen kaydın adı/ülkesi ve aday havuzunun tamamı.
Emin olamadıklarımı ayrı bir başlıkta **ŞÜPHELİ** olarak topladım — onları
ne doğru ne yanlış saydım.

İnceleme **228 `auto_match` kararının tamamını** kapsıyor. `review` / `ambiguous`
/ `no_match` kararları nihai karar değil, ertelemedir; onlar için "hata" kavramı
farklı işler (Bölüm 5).

---

## 1. Sonuç

| | satır | pay |
|---|---:|---:|
| `auto_match` | 228 | %45,6 |
| `review` | 201 | %40,2 |
| `ambiguous` | 49 | %9,8 |
| `no_match` | 22 | %4,4 |
| **gate'te tamamen biten** | **101** | **%20,2** |

### `auto_match` kesinliği

| | |
|---|---:|
| incelenen | 228 |
| **açık hata** | **14** |
| şüpheli | 5 |
| **kesinlik (şüpheliler doğru sayılırsa)** | **%93,9** |
| kesinlik (şüpheliler yanlış sayılırsa) | %91,7 |

**Hedef `≥ %98`. Ulaşılamıyor.** Ve bu satırlar hakeme gitmediği için hatalar
**sessizce** dışarı çıkıyor.

---

## 2. Açık hatalar (14)

| # | sorgu | seçilen | doğrusu |
|---|---|---|---|
| 7 | Kazakh National Pedagogical University named after Abay | `Pedagogical University` **[MZ]** | Abai Kazakh National Pedagogical Univ. [KZ] — **havuzda 2. sırada** |
| 24 | Akaki Tsereteli State University, Kutaisi, Georgia | `Kutaisi University` [GE] | Akaki Tsereteli State University — şehir adından eşleşmiş |
| 63 | Tanzania Police Staff College Kidatu | `Police Staff College` **[BD]** | Tanzanya'daki kurum |
| 198 | Polytechnic University of Bucharest | `University of Bucharest` [RO] | Politehnica — **havuzda 1. sırada** (`Universitatea Națională de Știință și Tehnologie`) |
| 227 | Başakşehir Çam ve Sakura City Hospital | `City Hospital` **[GB]** | İstanbul'daki hastane |
| 240 | T.C. Sağlık Bakanlığı Sincan Devlet Hastanesi | `Ministerio de Salud` **[CR]** | — |
| 253 | Sağlık Bakanlığı, Türkiye İlaç ve Tıbbi Cihaz Kurumu | `Ministerio de Salud` **[CR]** | — |
| 268 | TC Sağlık Bakanlığı Ordu Fatsa Devlet Hastanesi | `Ministerio de Salud` **[CR]** | — |
| 278 | T.C. Sağlık Bakanlığı Adana Eğitim ve Araştırma Hast. | `Ministerio de Salud` **[CR]** | — |
| 366 | Kutahya University of Health Science | `University of Health Science` **[KH]** | Kütahya Sağlık Bilimleri Üniversitesi |
| 375 | Imam Bonjol State Islamic University Padang | `Islamic University` **[BD]** | Universitas Islam Negeri Imam Bonjol Padang [ID] — **havuzda 2. sırada** |
| 435 | Bhai Gurdas Institution of Engineering and Technology | `Institution of Engineering and Technology` **[GB]** | Hindistan'daki kolej (IET UK bir meslek kuruluşu) |
| 441 | H. R. Patel Institute of Pharmaceutical Education, Shirpur | `Institute of Pharmaceutical Education and Research` **[UZ]** | Hindistan'daki enstitü |
| 458 | State Islamic University Imam Bonjol Padang | `Islamic University` **[BD]** | #375 ile aynı hata |

**Üç vakada doğru cevap havuzda duruyordu** (#7, #198, #375) — sistem onu görüp geçti.

## 3. Şüpheliler (5)

| # | sorgu | seçilen | neden şüpheli |
|---|---|---|---|
| 79 | Saint Columban College, Pagadian City | `Columban College` [PH] | Filipinler'de iki farklı kolej olabilir |
| 95 | Islamic Azad Univ., Science and Research Branch | `Islamic Azad University, Tehran` | farklı şube |
| 101 | Mahatma Gandhi Univ. of Medical Sciences and Tech. | `Mahatma Gandhi University` [IN] | Kerala vs Jaipur — farklı kurumlar |
| 357 | Amity University Chhattisgarh, Raipur | `Amity University` [IN] | ayrı kampüs/tüzel kişilik |
| 402 | Islamic Azad Univ., Damavand Branch | `Islamic Azad University, Tehran` | farklı şube |

Hepsi aynı sınıf: **kurum ailesi doğru, tekil kayıt yanlış olabilir.**

---

## 4. Hata örüntüleri

### 4.1 Jenerik ad tuzağı — 9/14

En büyük sınıf. Katalogda **kendi başına kimlik belirtmeyen** bir ad var
(`Pedagogical University`, `City Hospital`, `Islamic University`,
`Institution of Engineering and Technology`), sorguda o parça birebir geçiyor,
`exact_match` ateşliyor ve tek güçlü exact olduğu için `auto_match` çıkıyor.

Sorgunun **ayırt edici kısmı** (Kazakh National / Başakşehir Çam ve Sakura /
Imam Bonjol / Bhai Gurdas) hiç değerlendirilmiyor.

Gate'in mevcut koruması `MIN_EXACT_SPAN = 2` — yani "en az iki kelime". Ama
`city hospital` iki kelime, `institution of engineering and technology` beş
kelime. **Kelime sayısı ayırt edicilik değil.**

### 4.2 Kaynak veri defekti — 4/14

Dördü de aynı kayıt: `Ministerio de Salud` (Kosta Rika), alias listesinde
`Sağlık Bakanlığı` taşıyor. Bu bizim boru hattımızın ürettiği bir şey değil,
ham veride öyle geliyor (`DURUM.md` → "çok-kurumlu tek kayıt defekti", ERTELENDİ).

**Tek bir katalog kaydı, örneklemin %1,75'ini bozuyor.** 301.520 isimlik kuyrukta
bu ~5.300 satır demek.

### 4.3 Kardeş kurum karışması — 1/14

#198: `Polytechnic University of Bucharest` → `University of Bucharest`. Aynı
şehirde, benzer adlı, farklı üniversite.

---

## 5. Nihai olmayan kararlar (272 satır)

Bunlar hata değil, **erteleme**. Ama maliyet ve iyileştirme açısından üç gruba ayrılıyor:

| grup | ~satır | ne |
|---|---:|---|
| **kurtarılabilir** | ~100 | doğru cevap havuzda (tsr≥95) ama `exact_match` ateşlemiyor: akronim (`RTMNU`, `SBÜ`, `D.Ü.`), baş harf (`G. B. Pant` ↔ `Govind Ballabh Pant`), tire (`AlFarahidi` ↔ `Al-Farahidi`), yazım hatası (`Pertra` ↔ `Petra`) |
| **katalog kapsamı dışı** | ~60 | ilkokul/ortaokul, belediye birimi, federasyon, yayınevi, danışmanlık şirketi — katalogda yok, doğru cevap `no_match` |
| **gerçekten belirsiz** | ~49 | `ambiguous`: ikiz kayıtlar (Süleyman Demirel TR↔KZ), sorguda iki kurum (`Addis Ababa University, Hawassa University`), kurum+alt kurum |

`ambiguous` grubunun **%100'ü** gerçek kurum ifadesi taşıyor — o kova doğru çalışıyor.

**Not:** "kurtarılabilir" grubu benzerlik puanıyla otomatiğe alınamaz. Ayrı ölçtüm:
en güçlü 12 satırda kesinlik **~%75** (`Tehran` → `West Tehran Branch`,
`Fethiye A.S.M.K. MYO` → `Muğla MYO` gibi hatalar). %98 hedefi için yetersiz.

---

## 6. `token_set_ratio` defekti

İnceleme sırasında bulundu. **Kararı etkilemiyor, ama çıktıyı okuyan herkesi yanıltıyor.**

`token_set_ratio`, bir tarafın token kümesi diğerinin **alt kümesiyse 100** döner —
kalanın ne kadar açıklanmadığına bakmaz. Ve `_attach_signals` puanı **ad + tüm
alias'ların en iyisi** olarak alır. Sonuç: kısa ya da jenerik bir alias'ı sorguda
geçen her aday, ne kadar alakasız olursa olsun mükemmel puan alır.

Doğrulanmış vakalar:

| sorgu | aday | suçlu alias |
|---|---|---|
| `...Iran University of Science and Technology` | Korea Univ. of Sci. and Tech. [KR] | `"University of Science and Technology"` |
| `Central University of Karnataka...` | Universidad Central | `"Central University"` |
| `S DataM Bilişim... LTD. ŞTİ` | Superconductor Technologies [US] | `"STI"` |

Sonuncusu: Türkçe şirket eki **`ŞTİ`** → `sti`, Amerikan şirketinin akronimi
**`STI`** ile birebir çakışıyor.

**Ölçülen karar etkisi: sıfır.** 223 satırda tuzak adaylar çıkarılınca 0 satırda
karar değişti — çünkü kararın omurgası `exact_match`, `tsr` değil.

**Etkilediği yerler:** `signals` çıktısı, CSV denetim kolonları, `confidence`
sayısı (`score_candidate` doğrudan `tsr/100` kullanıyor), ve `display` adayı.
İlk analizimde beni de yanılttı.

Bu, bilinçli bir kararın (2026-07-24, alias'lara ayrı ayrı puanlama —
çapraz-dil kaçağını çözmüştü) **öngörülmemiş yan etkisi**; dikkatsizlik değil.

### İkincil bulgu: çelişkili denetim çıktısı

`review` satırlarında `neden=exact_yok` yazarken `exact_match=True, span=1`
görünüyor. Çelişki değil (gate "güçlü exact" için `span≥2` istiyor) ama denetim
çıktısı olarak yanıltıcı.

---

## 7. Hangi sinyal hangi hatayı yakalar

İki iyileştirme adayını 14 hataya karşı **ölçtüm**:

### Ayırt edicilik (df — eşleşen dizgeyi katalogda kaç kurum taşıyor)

```
#7   pedagogical university                        df= 74  YAKALAR
#227 city hospital                                 df= 98  YAKALAR
#375 islamic university                            df= 65  YAKALAR
#458 islamic university                            df= 65  YAKALAR
---
#24  kutaisi university                            df=  1
#63  police staff college                          df=  1
#435 institution of engineering and technology     df=  1
#366 university of health science                  df=  2
#198 university of bucharest                       df=  3
#441 institute of pharmaceutical education...      df=  3
#240/253/268/278  saglik bakanligi                 df=  7
```

**`df ≥ 20` eşiği 14 hatanın yalnızca 4'ünü yakalar.**

> Bu, benim önceki değerlendirmemi **düzeltiyor**. Daha önce df sinyalinin
> "11 bilinen yanlışı kapatacağını" söylemiştim — o ölçüm yalnızca ülke-çelişkili
> 10 satır üzerinden yapılmıştı ve o küme yüksek-df'li jenerik adlara yanlıydı.
> Tüm 228 auto incelenince kapsama **%29'a** düşüyor.

### Konum tutarlılığı (sorguda açık ülke ifadesi vs adayın ülkesi)

Yakalar: #63 (Tanzania→BD), #240/253/268/278 (T.C./Türkiye→CR) → **5/14**
Yakalamaz: #7, #24 (Georgia→GE, ülke **uyuşuyor**), #227, #366, #375, #435, #441, #458

**İkisi birlikte: ~8/14.** Hiçbiri tek başına yeterli değil.

---

## 8. Sonuçlar

1. **`auto_match` kesinliği %93,9 — hedef %98 tutmuyor.** Bu, gerçek üretim
   verisiyle ölçülmüş ilk sayı. Benchmark setinde durum daha iyi görünüyordu;
   gerçek veri daha kirli ve çok daha uluslararası.

2. **Kök neden `exact_match`'in ayırt edicilik körlüğü.** "Adı sorguda birebir
   geçiyor mu" sorusu, adın **kimlik belirtip belirtmediğini** sormuyor.
   `MIN_EXACT_SPAN` bunun için yetersiz bir vekil.

3. **Tek bir katalog kaydı hataların %29'unu üretiyor** (`Ministerio de Salud`).
   Kaynak veri defekti; kod tarafında çözülmesi gereken bir şey değil ama
   etkisi ölçüldü ve büyük.

4. **Önerdiğim iki sinyal de yetersiz.** df %29, konum %36 kapsıyor; birlikte
   ~%57. Kalan hatalar (`Kutaisi University`, `Police Staff College`,
   `Institution of Engineering and Technology`) **nadir ama jenerik** adlar —
   ne df ne ülke bunları ayırt ediyor. Bu sınıf için sorgunun **açıklanmayan
   kısmına** bakan bir ölçüt gerekiyor: aday sorgunun ne kadarını karşılıyor?

5. **Gate'te biten oran %20,2** — benchmark'taki %38,8'in yarısı. Kalan %79,8
   LLM'e düşerse 301.520 isimlik kuyruk bu donanımda ~67 gün sürer.

---

## 9. Kapsama oranı sinyali — ÖLÇÜLDÜ (2026-08-11)

Bölüm 8'de "1. öncelik, ölçülmeli" dediğim sinyal ölçüldü. Sonuç, beklentiyi
**kısmen doğruladı ama bedelini ortaya çıkardı**.

### 9.1 Naif tanım çalışmıyor

En basit hâli — *"aday sorgunun kaçta kaçını kapsıyor"* — hiçbir şey ayırmıyor:

```
ham kapsama orani:   DOGRU medyan 0,33   |   HATA medyan 0,33
```

Sebebi açık: doğru eşleşmelerde de sorgunun büyük kısmı kapsanmıyor.

```
"Department of Pediatric Nephrology, Faculty of Medicine, Ondokuz Mayıs University"
   -> "Ondokuz Mayıs Üniversitesi"  (DOGRU)
   acikta kalan: department, pediatric, nephrology, faculty, medicine   (9 token'in 6'si)
```

### 9.2 Çalışan varyant: kalan kelimeler *kurum ismi gibi mi*

Ayrım sözlükle değil **katalogdan**: bir token parent adlarında mı subunit
adlarında mı daha çok geçiyor (`df_parent` vs `df_subunit`). Kapsanmayan
token'lar arasında **parent-eğilimli ve nadir** olanların sayısı (M4) ayırıyor:

| | DOĞRU (n=209) | HATA (n=14) |
|---|---|---|
| M4 medyan | **1** | **3** |
| nadir-token kapsaması, p10 | 0,17 | 0,00 |

### 9.3 Takas tablosu (500 sorguda)

| kural | kalan auto | kesinlik | yakalanan hata | ek LLM | ek süre |
|---|---:|---:|---:|---:|---:|
| **müdahale yok** | 223 | **93,7%** | 0/14 | 0 | 0 |
| M4 ≥ 3 | 171 | 96,5% | 8/14 | 52 | 21 dk |
| M4 ≥ 2 | 147 | 95,9% | 8/14 | 76 | 30 dk |
| M4≥1 **ve** nadir-kapsama ≤0,34 | 157 | 97,5% | 10/14 | 66 | 26 dk |
| **M4 ≥ 1** | 104 | **99,0%** | 13/14 | 119 | 47 dk |
| nadir-kapsama ≤ 0,5 | 35 | **100%** | 14/14 | 188 | 75 dk |

### 9.4 Sonuç: bu bir düzeltme değil, bir takas

Sinyal gerçek ve hataların 13/14'ünü görebiliyor. **Ama ayrım keskin değil** —
doğru kararların yarısı da aynı örüntüyü gösteriyor, çünkü uzun affiliation
metinlerinde kapsanmayan kelime her zaman çok.

`≥ %98` hedefine ulaşan iki kural var, ikisi de ağır:
- **M4 ≥ 1** → kesinlik %99,0, ama `auto_match` **223 → 104** (%47'si kalır)
- **nadir-kapsama ≤ 0,5** → kesinlik %100, ama auto **223 → 35** (%16'sı kalır)

Yani hedef, mevcut `exact_match` omurgasıyla **ancak otomasyondan büyük ödün
vererek** tutuluyor. Ve o satırlar LLM'e düşerse, zaten darboğaz olan tarafı
daha da yükler.

**Bu bir mühendislik ayarı değil, ürün kararıdır:**

> %94 kesinlikle %46 otomasyon mu, %99 kesinlikle %21 otomasyon mu?

Cevap "yanlış bir otomatik eşleşmenin maliyeti" ile "bir satıra insanın
bakmasının maliyeti" oranına bağlı — bu, mühendislik tarafından belirlenemez.

---

## 10. Üç sinyalin toplu karnesi

| sinyal | 14 hatanın kaçını yakalar | bedeli |
|---|---:|---|
| ayırt edicilik (df ≥ 20) | 4 | ucuz |
| konum tutarlılığı | 5 | ucuz |
| **kapsama (M4 ≥ 1)** | **13** | **çok pahalı** (auto %53 düşer) |

**Hiçbiri bedava kazanç vermiyor.** Ucuz olan ikisi birlikte ~8/14 yakalıyor
ve kesinliği ~%96,5'e çıkarıyor — hedefin altında. Hedefi tutan tek yol
kapsama sinyalini sıkı ayarlamak, o da otomasyonu yarıya indiriyor.

---

## 11. Öneri

1. **Ürün kararı alınmalı** (Bölüm 9.4): hedef gerçekten `≥%98` mi, yoksa
   otomasyon oranı mı öncelikli? Bu netleşmeden eşik seçilemez.
2. **Ucuz iki sinyal (df + konum) yine de alınabilir** — ~8/14 yakalar,
   otomasyona etkisi küçük. Hedefi tutmaz ama bedava iyileşmedir.
3. **`Ministerio de Salud` sınıfı** — hataların %29'u tek bir katalog
   kaydından. Kod değil veri tarafı; en yüksek kazanç/emek oranı burada.
4. **`token_set_ratio` gösterim düzeltmesi** — karar etkisi yok, denetim
   güvenilirliği için.

**Metodoloji dersi:** bu incelemenin en net çıktısı, dar ve yanlı bir örneklem
üzerinden (10 ülke-çelişkili satır) çıkardığım sonucun tam inceleme yapılınca
**üçte birine** düşmesi oldu. Aynı şey kapsama sinyalinde de tekrarlandı:
"jenerik-ad tuzağının çoğunu hedefler" beklentisi doğru çıktı, ama yan etkisi
ancak ölçünce göründü. **Ölçmeden kural yazılmamalı.**
