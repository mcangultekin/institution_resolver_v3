# RAPOR — Çoklu-hipotez revizyonu: bulunan hatalar, yapılanlar, değişenler (2026-07-23)

> Bu rapor, "sistem istediğim gibi çalışmıyor, mimarisel sıkıntılar olabilir"
> şikâyetiyle başlayan oturumun TAM kaydıdır: teşhis → strateji kararı →
> tek tek bulunan hatalar (kanıtlarıyla) → yapılan kod/veri değişiklikleri →
> doğrulama sonuçları → bilinçli verilmeyen kararlar. İlgili deney günlüğü:
> `DENEY_2026-07-23_parent_dogrulama.md` (bir gün önceki geri alınan denemeler).
> Güncel durum özeti: `DURUM.md` bölüm "1b".

---

## 1. Başlangıç teşhisi: sorun tekil bug değil, MİMARİSEL

Projenin kendi değişmez ilkesi: **"ES'in işi aday bulmak, LLM'in işi seçmek."**
Ama mevcut kod fiilen tersini yapıyordu — SEÇİM, zincirin en başında, en zayıf
sinyalle, retrieval katmanında veriliyordu:

1. `decompose()` kurum sınırına **tek başına `fuzz.ratio`** (salt karakter
   benzerliği; anlam/tür/dil bilmez) ile karar veriyor ve **TEK bir sınır**
   seçiyordu.
2. `resolve()` bu tek tahmine dayanıp `parents[0]`'ı **tek sert "top parent"**
   kabul ediyor, subunit cascade filtresini yalnız ona bağlıyordu.
3. Hata zincirin sonuna kadar taşınıyordu; recall-güvenli birleşim doğru
   adayın *tamamen* kaybolmasını önlüyordu ama sıralama yanlılığı kalıyordu.

Bunun mimarisel (yapısal) olduğunun kanıtı, bir gün önceki iki başarısız
"yama" deneyiydi (bkz. deney günlüğü): parent-doğrulama mekanizması ve
embedding-yeniden-skorlama — ikisi de aynı noktayı retrieval İÇİNDE düzeltmeye
çalıştı ve ikisi de 50-sorguluk gerçek testte **yeni çekim-merkezi (attractor)
hataları** ekledi (büyük-subunit-kataloğu yanlılığı; embedding geometrisi).
Ders: erken katmandaki sert kararı aynı katmana sinyal ekleyerek düzeltmeye
çalışmak hep yeni bir yanlılık üretiyor.

## 2. Strateji kararı (kullanıcı, bu oturum): F2 YAPILMAYACAK

Kullanıcı etiketli değerlendirme seti (F2) yapmayacağını bildirdi. Bunun
mimari sonucu netti ve plan buna göre kuruldu:

- Etiket olmadan hiçbir "incelik ayarı" doğrulanamaz (aynı gün içinde iki kez
  kanıtlandı: 10 örnekte umut verici görünen sinyal, 50 örnekte net gerileme).
- Dolayısıyla retrieval'da hassasiyet/seçim optimizasyonu TAMAMEN bırakıldı.
- Retrieval'ın tek görevi: **recall'ü korumak** (doğru cevap havuzdan düşmesin).
- Seçim bütünüyle **F4 LLM hakeme** devredilecek — hakemin doğruluğu sorgu
  başına tek tek gözle denetlenebilir, küme-düzeyi metrik (etiketli set)
  gerektirmez. F2'nin yokluğunu en az hasarla karşılayan katman budur.
- Bu değişikliğin kendisi de etiket gerektirmeden doğrulanabilir, çünkü
  iddiası "daha doğru seçiyorum" değil, "doğru cevabı havuzdan düşürmüyorum"
  (evet/hayır göz kontrolü yeterli).

Uygulanan aksiyon planı: (1) decompose → hipotez modeli, (2) resolve →
çoklu-hipotezli birleşim, (3) 30-sorgu recall duman testi, (4) F4 hakem
iskeleti [sırada], (5) muhafazakâr gate [sırada].

---

## 3. BULUNAN HATALAR — tek tek, kanıtlarıyla

### H1. decompose tek sert karar veriyordu; `fuzz.ratio` bunu taşıyamıyor

- **Belirti (önceden bilinen, deney günlüğünden):** `"...Department of
  Educational Administration ... in Hacettepe University"` sorgusunda sınır
  "Department of Educational" seçildi (skor 95.8) — alakasız ama gerçek bir
  ROR kaydına ("Department of Education", K. İrlanda) neredeyse birebir
  örtüştüğü için doğru cevabı ("Hacettepe University", 90.5) yendi.
- **Kök neden:** `fuzz.ratio` uzunluk-duyarlı; kısa+tesadüfi örtüşen parça,
  uzun+doğru parçadan yüksek skor alabilir. 30-sorguluk marj deneyi (dün):
  %67 sorguda en iyi iki farklı-parent hipotezi arasındaki marj <10 — yani
  tek kazanan seçmek çoğu sorguda yazı-tura.
- **Yapısal sonuç:** yanlış tek seçim → yanlış parent → yanlış cascade
  filtresi → yanlış `[P]` işaretleri → hakem katmanına yanlı kanıt.

### H2. Cascade tek parent'a kilitliydi

`resolve()` yalnız `parents[0].id` ile subunit filtreliyordu. Decompose'un
birincil tahmini yanlışsa doğru kurumun subunit'i filtreden hiç geçmiyor,
yalnız filtresiz aramanın insafına kalıyordu (orada da genelde sıralamada
geriye düşüyordu).

### H3. Sinyal hatası: alternatif adayların `token_set_ratio`'su yanıltıcıydı
**(bu revizyon SIRASINDA doğan ve hemen yakalanan hata)**

Çoklu-hipotez birleşiminin ilk halinde her adayın tsr'ı KENDİ hipotezinin
kurum parçasına karşı hesaplanıyordu. Canlı çıktıda yakalandı:
`"gazi üniversitesi istatistik bölümü"` sorgusunda alternatif hipotez parçası
tek kelimelik `"üniversitesi"` olduğu için **Selçuk/Biruni/Boğaziçi tsr=100**
gösterdi (token_set_ratio alt-küme eşleşmesine 100 verir). Bu, F4 hakemine
doğrudan yanıltıcı kanıt olurdu.

- **Düzeltme:** parent sinyalleri (tsr + qualifier_conflict) TAM ORİJİNAL
  SORGUYA karşı hesaplanır. `token_set_ratio` sorgudaki fazla kelimeye zaten
  toleranslı → doğru parent tam sorguya karşı da 100 alır; tesadüfi
  tek-kelime örtüşmeleri düşer. Aynı sorguda doğrulandı: GAZİ tsr=100 kaldı,
  Biruni/Selçuk/Boğaziçi 72-77'ye indi.

### H4. Alias körlüğü — 30-sorgu duman testinin bulduğu ana kaçak sınıfı

- **Belirti:** `"JAMSTEC, Japan"` ve `"Westfälische Wilhelm University"`
  sorgularında doğru kayıt (Japan Agency for Marine-Earth Science and
  Technology, id 94840; University of Münster, id 12928) ne hipotezlerde ne
  parent havuzunda görünüyordu — korpusta alias'larıyla VAR oldukları halde
  (ES'te doğrulandı: 94840 alias "JAMSTEC"; 12928 alias "...Westfälische
  Wilhelms-Universität Münster...").
- **Kök neden:** ES BM25 araması `aliases_text`'ten kaydı BULUYORDU, ama
  decompose'un sınır skoru (`fuzz.ratio`) SADECE kanonik `name`'e karşı
  hesaplanıyordu → skor düşük → hipotez hiç doğmuyordu.
- **Aynı sınıfın veri-eksikliği alt-vakası:** `"Council of Forensic
  Medicine"` (= Adli Tıp Kurumu, id 65492) — kaydın İngilizce alias'ı hiç
  YOK; bu kod hatası değil veri eksikliği, kod tarafında çözülemez
  (ileride alias zenginleştirme işi).

### H5. Pencere başına top-5 aday yetmiyordu (alan-uzunluğu normu + fuzzy junk)

- **Belirti (canlı ölçüldü):** `search("JAMSTEC","parent")` sıralaması:
  Jastec 84.7, ADSTEC 78.9, AmpTec 75.6, Amtec 62.1, Memjet 35.7, ...
  **doğru kayıt 94840 ancak 7. sırada (22.4)**. Münster benzer şekilde 6.
- **Kök neden:** kısa adlı kayıtlarda fuzzy eşleşme (jamstec~jastec 1 edit)
  yüksek IDF + kısa-alan normuyla şişiyor; doğru kaydın exact-alias eşleşmesi
  uzun `aliases_text` alanının uzunluk normuna takılıyor. decompose pencere
  başına yalnız top-5'e baktığı için doğru kayıt hiç skorlanmıyordu.
- **Düzeltme:** `top_k` 5→10 (decompose default'u + resolve'daki dsf).
  Ek ES çağrısı YOK (aynı arama, daha büyük size); maliyet sadece pencere
  başına birkaç ucuz `fuzz.ratio` daha.

### H6. Kirli alias verisi: virgülle birleşmiş çoklu adlar

- **Belirti:** H4-H5 düzeltmelerinden sonra bile Münster hipotez üretemedi.
- **Kök neden (canlı doğrulandı):** kayıttaki alias değeri
  `"Universitaet Muenster, Westfälische Wilhelms-Universität Münster"` —
  virgülle birleşmiş İKİ ad TEK alias olarak duruyor (ham ROR verisi; DURUM
  P6 notundaki "kalan virgüller yabancı kurum adları" tespitiyle tutarlı).
  Temiz "Westfälische Wilhelms-Universität Münster" ayrı alias olarak yok;
  birleşik dizgeye karşı ratio düşük kalıyor (~60'lar), oysa segmente karşı
  83.3.
- **Düzeltme:** decompose skorlamasında her alias'ın virgül-segmentleri de
  ek varyant olarak denenir — ama **yalnız ≥2 kelimelik segmentler**.
  Tek kelimelik segment şartı bilinçli: "Jastec Co., Ltd. (Japan)" gibi
  adlardan kopan "Ltd." parçası, "ltd/şti" içeren şirket sorgularında 100'lük
  tesadüfi çekim merkezi olurdu (dünkü deneyin bilinen tuzak sınıfı).

### H7. Hipotezin parent'ı aday listesinde görünmüyordu

- **Belirti:** JAMSTEC düzeltmesinden sonra H0 doğruydu ve cascade doğru
  çalışıyordu, ama 94840 `parents` listesinde YOKTU — çünkü parent havuzu
  araması ("JAMSTEC," penceresiyle BM25+kNN, size=5) onu top-5'e sokmuyordu.
  Hakem, hipotezin işaret ettiği kaydı aday olarak hiç göremeyecekti.
- **Düzeltme:** `_parent_union` sonunda, havuzda olmayan hipotez parent'ları
  asgari sinyallerle **enjekte edilir**: `bm25_norm=0.0` (listeye girmedi),
  `cosine=None` (ölçülmedi — 0.0 ile karıştırılmaz, mevcut sözleşme),
  tsr/qualifier tam sorguya karşı hesaplanır, `raw.from_hypothesis_only=True`
  bayrağıyla işaretlenir.

### H8. Revizyonun kendi yan etkisi: kısa-token akronim tuzağı → Çanakkale regresyonu
**(30-sorgu tekrar-testinin yakaladığı, düzeltilen regresyon)**

- **Belirti:** alias-farkındalıklı skor açılınca `"Çanakkale 18 Mart
  Üniversitesi ... Ana Bilim Dalı"` sorgusunda tek-tokenlik `"Ana"` penceresi
  "ANA Aeroportos de Portugal"ın `ANA` alias'ına **100** aldı ve H0 oldu;
  `"Mart"`→SMART (88.9 fuzzy), `"Mart Üniversitesi"`→MARMARA (86.5) derken
  doğru hipotez (ÇANAKKALE ONSEKİZ MART ÜNİVERSİTESİ, 86.2) top-3 DIŞINA
  düştü — hem hipotezlerden hem parent havuzundan hem cascade'den kayboldu.
  Benzer: `"Şti"`→STI Electronics 100, `"KAMU"`→Kumi University 75.
- **Neden eşik/kural ile ÇÖZÜLMEDİ:** "gerçek akronim sorgusu" (JAMSTEC,
  JSTER) ile "tesadüfi kısa token" (Ana, Şti) FORMDAN ayırt edilemez —
  karakter-uzunluğu eşiği ODTÜ gibi meşru 4-harfli akronimleri de öldürür,
  ve eşik ayarı etiketli set gerektirir (F2 yok). Bu ayrım tam olarak LLM
  hakemin işi.
- **Uygulanan yapısal (eşiksiz) çare:** görev "doğruyu seçmek" değil "doğruyu
  LİSTEDE TUTMAK" olduğu için kapasite artırıldı: `MAX_HYPOTHESES` 3→5,
  `MAX_CASCADE_PARENTS` 4→6. Doğrulama: Çanakkale artık H3'te, parent
  havuzunda (tsr=87.1) ve doğru subunit (`ORTOPEDİ VE TRAVMATOLOJİ ANABİLİM
  DALI` ← Çanakkale) `[P]` bayrağıyla 2. sırada.

### H9. (Sınıflandırma) Korpusta-hiç-yok vakaları — kod hatası DEĞİL

30-sorgu setinde ~6-8 sorgunun doğru cevabı korpusta yok; bunlarda "yanlış
sonuç" değil `no_match` beklenir (F4 hakemin görevi):
- `İzmir Büyükşehir Belediyesi` — korpusta yok (İstanbul/Kocaeli/Bursa/Ordu var).
- `Süleyman Şah Üniversitesi` (kapatılmış vakıf üniv.) — yok.
- `KAMU DENETÇİLİĞİ KURUMU`, `JSTER` (dergi), `Dermoda ... Ltd. Şti` (şirket),
  `Federal School of Medical Laboratory Science Jos` (kısmen — benzer adlı
  "Federal College of Medical Laboratory Science and Technology" var, alias
  eşleşmesi artık onu buluyor), `Trabzon Kanuni ... Hastanesi` (parent olarak
  yok; SBÜ altında subunit 49061 olarak VAR — filtresiz subunit aramasında
  top-1, yani bu vaka aslında kurtarılıyor).

---

## 4. YAPILAN DEĞİŞİKLİKLER — dosya dosya

### `retrieve/decompose.py`
- **Yeni veri modeli:** `BoundaryHypothesis` dataclass'ı; `DecomposedQuery`'ye
  `hypotheses: list[BoundaryHypothesis]` alanı. Birincil alanlar
  (`institution_part/unit_part/boundary_score/matched_parent_*`) =
  `hypotheses[0]`'ın kopyası → **geriye dönük uyumlu** (eski tüketiciler
  kırılmaz).
- **Algoritma:** tek global kazanan yerine `best_by_parent` — her parent_id
  için en iyi (skor, uzunluk, ilk-görülme) pencere tutulur; sıralama eski
  global-kazanan mantığının birebir genellemesi (skor > uzunluk > ilk görülen),
  top `MAX_HYPOTHESES=5` farklı parent hipotez olur. Hipotezler SIRALANIR ama
  asla ELENMEZ/yeniden seçilmez (dünkü geri alınan "doğrulama" deneyinin
  tuzağından bilinçli kaçınma — docstring'de belgeli).
- **Alias-farkındalıklı skor:** `_name_variants(hit)` — name + her alias +
  alias'ların ≥2-kelimelik virgül-segmentleri; skor bunların maksimumu.
  Birleşik `aliases_text`'e `partial_ratio` bilinçli KULLANILMADI (tek
  kelimelik jenerik pencere her birleşik metinde 100 bulur — çekim-merkezi
  tuzağı; gerekçe mappings.py'de de belgeli).
- `top_k` default 5→10; `MAX_HYPOTHESES=5` sabiti (gerekçe yorumda).
- Docstring'e "KARAR DEGIL HIPOTEZ" bölümü eklendi (neden, kanıt, dünkü
  deneyle ilişkisi).

### `retrieve/resolve.py`
- **`_parent_union(decomposed, query, ...)`:** her hipotezin kurum parçasıyla
  AYRI parent araması (BM25+kNN+RRF); recall-güvenli birleşim — birincil
  hipotez `size` kadar, sonraki her hipotez havuzda OLMAYAN ilk
  `ALT_HYPOTHESIS_CONTRIB=3` adayını ekler; aynı kurum-parçası tekrar
  aranmaz (dedup). bm25_norm her aramanın KENDİ içinde normalize edilir
  (farklı sorgu metinlerinin ham BM25'leri karşılaştırılamaz).
- **Sinyal düzeltmesi (H3):** parent adaylarının tsr/qualifier'ı hipotez
  parçasına değil TAM sorguya karşı.
- **Hipotez-parent enjeksiyonu (H7):** havuza girememiş hipotez parent'ları
  asgari sinyalle eklenir (`from_hypothesis_only=True`).
- **`_cascade_parent_ids`:** cascade artık tek parent değil — en güçlü parent
  adayı + tüm hipotez parent'ları (sıralı, tekrarsız, ≤`MAX_CASCADE_PARENTS=6`)
  tek `terms` filtresiyle: `{"terms": {"parent_id": [...]}}` (tek ES çağrısı,
  parent başına ayrı arama YOK). Filtresiz arama ve recall-güvenli birleşim
  (`_merge_filtered_first`) aynen korundu.
- Modül docstring'i yeni akışa göre yeniden yazıldı.

### `elastic/mappings.py` + `elastic/document.py` (+ REINDEX)
- Mapping'e `aliases` alanı: `{"type": "keyword", "index": False,
  "doc_values": False}` — **aramaya kapalı**, yalnız `_source`'ta taşınır
  (aramayı `aliases_text` yapmaya devam eder; skor ayrı-liste ister).
- `build_document` artık `aliases: [...]` listesini de yazar
  (`aliases_text` aynen kalır).
- **Reindex yapıldı:** `setup-es` (index yeniden yaratıldı) + `index
  --embeddings` → 231.291 kayıt (106.183 parent + 125.108 subunit), 0 hata;
  embedding'ler `data/processed/embeddings.npz` cache'inden geldi (encode
  tekrarı yok).

### `cli/main.py`
- `match` komutu artık TÜM hipotezleri listeler ("decompose hipotezleri
  (secim yok, hepsi havuza katilir)" + H0..H4 satırları). Tek-karar
  gösterimi kaldırıldı — dünkü deneyin "gösterilen ≠ kullanılan" tutarsızlık
  dersinin (deney günlüğü sorun B) gereği: gösterim, iç durumun birebir
  yansıması.

### Testler (108 → 119, hepsi yeşil)
- `test_decompose.py`: hipotez testleri (birincil=hypotheses[0] aynası,
  farklı-parent garantisi, skor sıralaması, alternatiflerin listede kalması);
  akronim-alias testi (JAMSTEC senaryosu: alias'tan hipotez doğuyor, skor
  100); sahte arama artık alias token'larını da indeksliyor (gerçek ES
  davranışına sadakat).
- `test_resolve.py`: `TestMultiHypothesisCascade` — `terms` filtresinin
  alternatif hipotez parent'larını kapsadığı, alternatif parent'ın
  subunit'inin filtreden geçtiği (`passed_parent_filter=True`), birleşimde
  birincilin önde kaldığı; H7 enjeksiyon testi (havuz boşken hipotez parent'ı
  asgari sinyallerle listede).
- Eski 8 decompose + 7 resolve testi DEĞİŞMEDEN geçiyor → geriye dönük
  uyumluluk testle kanıtlı.

### `docs/DURUM.md`
- Bölüm "1b. Çoklu-hipotez revizyonu" eklendi; F2 satırı "İPTAL (kullanıcı
  kararı)" olarak güncellendi; build-order tablosuna 1b satırı eklendi.

---

## 5. DOĞRULAMA — önce/sonra

### Birim testleri
108 → **119 test, tümü yeşil** (`python3 -m pytest tests/unit -q`).

### 30-sorgu duman testi (isimler_tekrarsız.csv, seed=42, aynı örneklem, gözle değerlendirme)

Ölçüt etiketsiz ve ikili: "doğru cevap ilk 10 adayda (parent veya subunit) var mı?"

**ÖNCE → SONRA düzelen vakalar (retrieval kaçağıydı, artık havuzda):**

| # | Sorgu (kısaltılmış) | ÖNCE | SONRA |
|---|---|---|---|
| 9 | KTO KARATAY UNIVERSITY... | H0 Karnatak University (yanlış) | H0 KTO KARATAY 100 |
| 10 | Federal School of Medical Laboratory Science Jos | havuzda alakalı kayıt yok | H0 Federal College of Medical Laboratory Science and Technology (alias) |
| 17 | MUSTAFA KEMAL UNIVERSITY, FACULTY OF AGRICULTURE... | H0 "ENGINEERING"→JHV Engineering; parent top-6 tamamen çöp | H0 HATAY MUSTAFA KEMAL 89 |
| 26 | Department of Chemical Engineering, Istanbul Technical University | H0 Navajo Technical University; İTÜ ancak H2 | H0 İSTANBUL TEKNİK ÜNİVERSİTESİ 100 |
| 27 | JAMSTEC, Japan | doğru kayıt hiçbir yerde yok | H0 Japan Agency for Marine-Earth... 100 + parents'ta + cascade'de |
| 29 | Westfälische Wilhelm University | doğru kayıt hiçbir yerde yok | H0 University of Münster 83.3 + parents'ta + subunit'i [P] |
| 12 | Institute of Bioorganic Chemistry named after A.S.Sadykov... | H0 doğru ama 84'lük gürültülü | H0 100 (alias) |

**Regresyon olarak doğup DÜZELTİLEN vaka:**

| # | Sorgu | Ara durumda | Nihai |
|---|---|---|---|
| 20 | Çanakkale 18 Mart Üniversitesi ... Ana Bilim Dalı | "Ana"→ANA Aeroportos H0=100; Çanakkale hipotez/havuz/cascade'den tamamen düştü | MAX_HYPOTHESES=5 ile H3'te; parents'ta tsr=87.1; doğru subunit [P] 2. sıra |

**Değişmeden iyi kalanlar (gerileme yok):** #2 Batman, #3 Hatay M. Kemal,
#7 Giresun, #8 Bartın, #11 İst. Aydın, #15 AYBÜ, #16 Vrije (doğru kayıt
H1 + parents 3. sıra), #18 Antalya AKEV→Belek (alias), #19/#24 Ankara,
#21 Miskolc, #28 İstinye, #30 Afyon Kocatepe.

**Korpusta-yok / veri-eksikliği (kod dışı):** #1 (Adli Tıp Kurumu İngilizce
alias'ı yok), #4, #5, #6 (belirsiz sorgu), #13 (Süleyman Şah yok), #14, #22,
#23, #25 — bunlarda beklenen çıktı `no_match`/`review`, karar F4'ün işi.

**Net tablo:** ~24/30 recall başarısı; kalan ~6 vaka retrieval hatası DEĞİL
(korpus kapsamı ya da sorgunun kendisi belirsiz).

### Canlı nokta doğrulamaları
- `gazi üniversitesi istatistik bölümü` — H0 doğru 100; doğru subunit [P] top-1;
  H3 düzeltmesi sonrası tesadüfi adayların tsr'ı 100→≤77.
- `Trabzon Kanuni Eğitim ve Araştırma Hastanesi` — parent olarak korpusta yok
  ama doğru cevap subunit 49061 (SBÜ) filtresiz havuzda top-1 → recall-güvenli
  birleşim işini yapıyor; seçim hakeme kalıyor.
- `Gazi University Faculty of Pharmacy` — eskiden "Gazi University" penceresi
  tamamen düşüyordu; şimdi H0 Ghazi University (Pakistan, 96.8) yanlış olsa da
  GAZİ ÜNİVERSİTESİ hem H2'de hem parent havuzunun tepesinde (bm25=1.0).

---

## 6. BİLİNÇLİ verilen/verilmeyen kararlar ve kabul edilen yan etkiler

1. **Hipotezler elenmez, sıralanır.** Dünkü geri alınan deney, retrieval
   içinde "seçim" yapmanın (subunit kanıtıyla bile) yeni yanlılık doğurduğunu
   gösterdi; bu revizyon o hattı bilinçli olarak KAPALI tutuyor.
2. **Kısa-token akronim tuzağı KABUL EDİLDİ** (H8): "Ana"→ANA gibi çöp H0'lar
   kalabilir. Eşik/kural ile ayırt edilemez (ODTÜ vakası; F2 yok). Güvence:
   doğru hipotez 5'lik listede + 6'lık cascade'de + enjeksiyonla parents'ta.
   Seçim F4 hakemin işi.
3. **`partial_ratio` yasak** (birleşik aliases_text'e karşı) — gerekçe H6'da.
4. **Eşik hâlâ YOK** — hiçbir yeni sabit "güven eşiği" eklenmedi;
   `MAX_HYPOTHESES/MAX_CASCADE_PARENTS/ALT_HYPOTHESIS_CONTRIB/top_k` kapasite
   sabitleridir (recall'ü genişletir, hiçbir adayı elemez).
5. **Maliyet:** decompose hâlâ O(n²) ES çağrısı (alt-dizge taraması) +
   hipotez başına ≤2 ek havuz araması. Batch ölçeği etkisi F5'te ölçülecek
   (`_msearch` seçeneği DURUM'da açık karar olarak duruyor).
6. **Alias verisi kirli** (virgül-birleşik değerler): decompose tarafında
   segment-varyantla telafi edildi; kalıcı temizlik (ingest'te alias split)
   yapılMADI — ingest pipeline'ına dokunmak bu revizyonun kapsamı dışıydı,
   ileride P-adımı olarak değerlendirilebilir.
7. **Adli Tıp Kurumu sınıfı** (İngilizce alias hiç yok): kod tarafında
   çözülemez; alias zenginleştirme ayrı bir veri işi olarak not edildi.

## 7. SIRADAKİ İŞLER (aksiyon planının kalanı)

4. **F4 — LLM hakem iskeleti:** `judge/` paketi; adaylar + sinyaller
   (`ScoredCandidate` alanları tam da bunun için: bm25_norm, cosine(None
   ayrımıyla), token_set_ratio, qualifier_conflict, passed_parent_filter,
   from_hypothesis_only) → tek Anthropic çağrısı →
   `auto_match/review/ambiguous/no_match` + JSON. Yetki asimetrisi: LLM
   sadece DÜŞÜRÜR, deterministik kanıt yükseltir. Bekleyen: API anahtarı
   ortamda mı + model tercihi (öneri: claude-sonnet-5).
5. **Muhafazakâr gate:** yalnız bariz birebir eşleşme auto, gerisi hakeme
   (eşik ayarı gerektirmez).
6. Commit: bu revizyon bütün halinde commitlenmeye hazır (kullanıcı onayı
   bekliyor).
