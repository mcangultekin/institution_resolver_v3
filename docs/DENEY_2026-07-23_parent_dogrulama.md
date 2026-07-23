# Deney günlüğü — parent doğrulama mekanizması (2026-07-23)

> Son commit (`7857a50`) sonrası bu oturumda yapılan tüm kod değişiklikleri
> **geri alındı** (`git checkout`). Bu dosya, neyin denendiğini ve neden
> vazgeçildiğini kaydetmek için var — aynı fikir tekrar denenirse buradaki
> tuzaklara düşülmesin diye.

## Başlangıç noktası: decompose'un bilinen zayıflığı

`retrieve/decompose.py`, kurum sınırını `rapidfuzz.fuzz.ratio` (salt karakter
dizisi benzerliği) ile buluyor — anlam/tür bilmiyor. Canlı örnekle doğrulandı:

```
"the Department of Educational Administration, Supervision, Planning and
 Economics in Hacettepe University, Turkey."
```

decompose kurum sınırını **"Department of Educational"** olarak seçti (skor
95.8), gerçek cevap **"Hacettepe University"**yi (skor 90.5) geçti — çünkü
"Department of Educational" tesadüfen alakasız ama gerçek bir ROR kaydına
("Department of Education", Kuzey İrlanda bakanlığı, id 23012) neredeyse
birebir örtüştü. Kök neden: `fuzz.ratio` uzunluk farkına duyarlı, kısa+tesadüfi
örtüşen bir parça, uzun+doğru bir parçadan daha yüksek skor alabiliyor.

## 30 sorguluk marj deneyi

`isimler_tekrarsız.csv`'den (v2) rastgele 30 sorguda decompose'un en iyi
skorla (farklı bir parent'a işaret eden) ikinci en iyi skoru arasındaki
**marj** ölçüldü (bkz. `margin_probe.py`, artık silindi).

- 20/30 (%67) sorguda marj <10.
- Düşük marjlı grupta hata oranı gözle görülür şekilde yüksekti (~13/20).
- Ama yüksek marj da güven vermiyor: `JSTER`, `JAMSTEC`, `Dermoda Deri
  Tekstil...` gibi korpusta muhtemelen hiç olmayan kurumlarda marj yapay
  olarak yüksek çıktı (tek zayıf eşleşme "yalnız" durduğu için).

**Çıkarım:** marj tek başına "belirsizlik" sinyali olarak kullanılabilir ama
"doğruluk" garantisi vermiyor — iki farklı hata modu (belirsizlik vs.
korpusta-hiç-yok) marjla ayrıştırılamıyor.

## Denenen çözüm: parent doğrulama (subunit kanıtıyla çapraz kontrol)

Fikir: decompose birden fazla farklı-parent adayı buluyorsa (`alternates`),
her birini kendi `parent_id`'siyle filtrelenmiş subunit aramasından geçirip,
hangisinin subunit kanıtı daha güçlüyse onu seç.

Uygulama: `decompose.py`'ye `DecomposeAlternate` + `DecomposedQuery.alternates`
eklendi (en, farklı parent'lara işaret eden top-3 aday). `resolve.py`'ye
`_verify_parent_candidates` + `ParentVerification` eklendi.

### Yol boyunca bulunan/düzeltilen hatalar

1. **Öz-normalizasyon hatası:** İlk halde `_branch_confidence`, her dalın
   `bm25_norm`'unu KENDİ İÇİNDEKİ en yükseğe bölüyordu — bu, zayıf bir dalın
   tek sonucunu bile otomatik ~1.0'a şişiriyordu (dallar arası karşılaştırma
   anlamsızlaşıyordu). Düzeltme: `token_set_ratio` + `cosine` gibi
   **mutlak/karşılaştırılabilir** ölçeklere geçildi. Canlı testte Hacettepe
   ve KTO Karatay örnekleri bu düzeltmeden sonra doğru sonuç verdi.

2. **`unit_part` boşken zorla doğrulama:** `"Vrije University Amsterdam"`
   gibi sadece-kurum-adı sorgularında, karşılaştıracak gerçek bir birim
   yokken mekanizma yine de subunit dallarını kıyasladı; doğru cevabın
   (`Vrije Universiteit Amsterdam`) hiç subunit'i yoktu (kanıt=0.0), yanlış
   adayın (`University of Amsterdam`) ise ES'in eşiksiz kNN'i yüzünden
   alakasız ama orta-yüksek kosinüslü bir subunit'i vardı → yanlış kazandı.
   Düzeltme: `unit_part` boşsa doğrulamayı atla. (Not: bu düzeltme yarım
   kaldı — decompose'un kendisi bazen tek bir "artık" kelime bırakıyor,
   ör. "Vrije" — bu durumda `unit_part` boş SAYILMIYOR ve doğrulama yine
   yanlış tetikleniyor. Ayrıca veri kontrolü: korpusta bu kurumun ne
   `"Vrije University Amsterdam"` ne de `"...of Amsterdam"` alias'ı vardı,
   sadece Hollandaca `"Vrije Universiteit Amsterdam"` — yani bu spesifik
   test örneği kısmen veri eksikliğinden de kaynaklanıyordu.)

## 50 sorguluk gerçek-veri testi — asıl karar noktası

`isimler_tekrarsız.csv`'den 50 rastgele sorguda tüm pipeline (decompose +
doğrulama) canlı ES'te çalıştırıldı, sonuçlar tek tek elle değerlendirildi.

**Sonuç: 17/50 yanlış (%34)**, 1 sorgu değerlendirme dışı (`"Kütahya"` — tek
kelime, gerçek kurum ifadesi yok).

Üç ayrı, örtüşen sorun tespit edildi:

### A. Doğrulama mekanizmasının kendisi yeni ve sistematik bir yanlılık yarattı

`Koç Üniversitesi`, `Ege Üniversitesi`, `University of Bern`,
`University of Fribourg` gibi **subunit kataloğu büyük/çeşitli** kurumlar,
tamamen alakasız sorgularda bile tekrar tekrar "kazanan" çıktı:

- `"Mardin Artuklu Üniversitesi Sosyal Bilimler Enstitüsü"` → decompose
  doğru bulmuşken (Mardin Artuklu, skor 100.0) doğrulama **Koç
  Üniversitesi'ni** (skor 85.7) seçti.
- `"Anadolu Üniversitesi Fen Fakültesi Biyoloji Bölümü"` → aynı şekilde
  Koç kazandı, Anadolu (100.0) kaybetti.
- `"Obafemi Awolowo University"` (Nijerya) → **University of Bern**
  (İsviçre) kazandı.
- `"COMSATS University, Abbottabad"` (Pakistan) → yine **University of
  Bern** kazandı.

**Kök neden:** doğrulama her dalın SADECE en iyi tek subunit'ine bakıyor.
Bir kurumun subunit havuzu ne kadar büyük/çeşitliyse, o havuzda rastgele
bile olsa yüksek kosinüslü BİR sonuç bulma ihtimali o kadar artıyor — bu
"gerçek kanıt" değil, istatistiksel bir şans avantajı. Buna karşın doğru
cevap (küçük/subunit'i az olan bir kurum) genelde `subunit_kanit=0.000`
alıp haksız yere eleniyor.

### B. Ayrı bir uygulama hatası: gösterim tutarsızlığı

`ResolveResult.parents[0]` (CLI'da "SECİLEN PARENT" satırı), doğrulamanın
gerçek kazananıyla (`top_parent_id`, subunit filtrelemede kullanılan)
**her zaman aynı değildi**. Sebep: kazanan zaten `parents` listesinde
(sadece ilk sırada değil) varsa, kod listeyi yeniden sıralamıyordu — sadece
kazanan listede HİÇ yoksa ekliyordu. En az 8 sorguda (`#16, #19, #23, #26,
#31, #37, #39, #50`) gösterilen parent, gerçekte kullanılan parent'tan
FARKLIYDI — hata ayıklamayı doğrudan yanıltan bir tutarsızlık.

### C. Önceden bilinen decompose sorunu tekrar gözlendi

Kritik niteleyici kelimeler bazen pencereye dahil edilmiyor:
- `"Trabzon Kanuni Eğitim ve Araştırma Hastanesi"` → "Trabzon Kanuni" düştü,
  jenerik "Eğitim ve Araştırma Hastanesi" kaldı → yanlış şehir.
- `"Gazi University Faculty of Pharmacy"` → "Gazi University" tamamen düştü.
- `"izmir büyükşehir belediyesi"` → "izmir" düştü.

## Karar: geri alındı

Doğrulama mekanizması küçük örneklerde (Hacettepe, KTO Karatay, Ondokuz
Mayıs, Ankara Üniversitesi/Veterinary) gerçekten işe yaradı, ama 50 sorguluk
gerçek örneklemde **eklediği yeni hata (A: büyük-kurum yanlılığı) muhtemelen
düzelttiğinden daha fazla soruna yol açtı**. Kullanıcı kararıyla tüm kod
değişiklikleri (`decompose.py`, `resolve.py`, `cli/main.py`) son commit'e
(`7857a50`) geri döndürüldü. Kod tabanında bu deneyden **hiçbir iz kalmadı** —
sadece bu belge kaldı.

## Ek deney: embedding/vektör ile skorlama (aynı gün, ayrı deneme)

Doğrulama mekanizması geri alındıktan sonra, farklı bir fikir denendi: decompose'un
`fuzz.ratio` skoruna ek olarak, en iyiye YAKIN (marj küçük) adaylar arasında
**embedding kosinüs benzerliği** ile ikinci bir eleme yapmak (kod tabanına
hiç dokunmadan, bağımsız bir prototip script ile). Gerçek repo dosyaları
değişmedi, prototip artık silindi — bu bölüm sadece sonucu kaydediyor.

**Yöntem farkı önemli:** ilk denemede aday PENCERESİNİN (decompose'un seçtiği
dar metin parçası) embedding'i kullanıldı — bu, `ratio` ile aynı "dar bağlam"
zayıflığını miras aldı (pencere zaten kritik kelimeyi (ör. üst kurumun adını)
içermiyorsa embedding de onu göremiyor). Düzeltme: **tüm orijinal sorgunun**
embedding'i tek seferde hesaplanıp adayların isimleriyle kıyaslandı — bu,
küçük bir 10 sorguluk örneklemde umut verici sonuç verdi (4 düzeltme, 0 gerileme).

**50 sorguluk gerçek testte tam tersi çıktı:** 15/50 sonuç değişti, ama
**5 gerileme (önceden doğruyken yanlış oldu) vs 3 iyileşme** — net olarak
mevcut (embedding'siz) sistemden DAHA KÖTÜ. Kök nedenler:

1. Birleştirme mantığı (cosine birincil, ratio sadece eşitlik bozucu) hatalıydı:
   milyonda birlik bir cosine farkı (ör. `0.888975` vs `0.889225`), **%100
   birebir string eşleşmesini** geçersiz kılabiliyordu. Bu, sinyallerin
   ağırlıklandırılmasında temel bir tasarım kusuruydu.
2. Aynı kurum (belirli bir tekrar eden hatalı aday), üç ayrı alakasız sorguda
   doğru kazananın yerini çaldı — subunit-kataloğu büyüklüğü sorununa BENZER
   ama farklı bir mekanizmadan (embedding geometrisi) kaynaklanan yeni bir
   "çekim merkezi" (attractor) deseni.
3. Küçük örneklemde (10 sorgu) iyi görünen bir sinyal, büyük örneklemde (50
   sorgu) tersine döndü — bugünkü ikinci kez aynı ders.

**Karar:** bu da geri alındı/silindi, koda hiç işlenmedi.

## Bir dahaki sefere denenecekse — öğrenilenler

1. **Tek-subunit kanıtı yerine, dalın subunit KALİTESİNİ/havuzunun kendi
   içindeki dağılımını** ölçen bir yöntem gerekir — ör. top-K ortalaması,
   ya da "bu subunit gerçekten sorgunun geri kalanına mı benziyor yoksa
   genel olarak yüksek-benzerlikli bir kurum mu" ayrımını yapan bir
   normalizasyon (kurum büyüklüğünden bağımsız).
2. **`unit_part` boş kontrolü tek başına yeterli değil** — decompose'un
   kendi pencere hatası (tek kelime "artık" bırakması) bu kontrolü atlatıyor.
   Belki "birim ifadesi anlamlı mı" sorusu, `unit_part` uzunluğundan çok,
   decompose'un kendi `boundary_score`'unun ne kadar net olduğuna bakılarak
   sorulmalı.
3. **Gösterim/tutarlılık ayrı test edilmeli** — "sistem ne seçti" sorusunun
   TEK bir doğru kaynağı olmalı (ya `parents[0]` ya da doğrulama sonucu, ikisi
   asla çelişmemeli). Bu oturumda bu ayrım net değildi, hata ayıklamayı
   zorlaştırdı.
4. **F2 (gerçek etiketli set) hâlâ öncelik.** Bu deney, körü körüne
   iyileştirme denemenin (etiketsiz veriyle bile) ne kadar çabuk yanlış
   yöne gidebileceğini gösterdi — 50 sorguluk gözle-değerlendirme bile
   (gerçek etiketli set değil) üç ayrı sorunu ortaya çıkardı. Sistematik,
   tekrarlanabilir ölçüm olmadan bu tip mekanizmalar eklemek riskli.
