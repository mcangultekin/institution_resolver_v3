# Fable Retrospektifi — Bağımsız Yeniden Değerlendirme

> Tarih: 2026-07-17. Yazan: Claude (Fable 5), tamamen bağımsız bir okuma turunda.
> Girdiler: REBUILD_GUIDE.md (hipotez kaynağı olarak — nihai cevap olarak DEĞİL),
> EXPERIMENTS.md'nin tamamı (F5-sonrası ilk ince ayardan Faz 3.7 kapanışına),
> REVIEW_RAPORU.md, ACTION_PLAN.md, README.md, git log (28 commit), src/ kodu,
> ve `data/raw/` üzerinde bu oturumda YENİDEN koşulmuş ölçümler (script:
> scratchpad/verify_claims.py, projenin kendi `_simple_normalize`'ı ile).
> Not: `institution_resolver_v2_tasarim.md` bu turda da bulunamadı (repo +
> Desktop tarandı) — REVIEW_RAPORU.md'nin 2026-07-15 tespiti hâlâ geçerli.

---

## 1. REBUILD_GUIDE.md iddia doğrulaması — ne teyit edildi, ne çürüdü

Rehberin sayısal iddiaları bu oturumda ham CSV'ler üzerinde yeniden ölçüldü.
Sonuç: **çekirdek veri iddiaları neredeyse birebir doğru; iki iddia yanlış/
yanıltıcı ifade edilmiş; durum-tespiti bölümü (Bölüm 6) ise tamamen bayat.**

### 1.1 Birebir teyit edilenler

| İddia (REBUILD_GUIDE) | Yeniden ölçüm (2026-07-17) | Hüküm |
|---|---|---|
| Subunit 179.106 satır / 138.298 aktif; parent 106.331 | 179.106 / 138.298 / 106.331 | ✅ birebir |
| Aynı `(parent_id, normalized_name)`: **5.333 grup, 13.557 fazla aktif satır** | 5.333 grup, 18.890 üye, 18.890−5.333 = **13.557 fazla** | ✅ birebir |
| SBÜ altında **165× "ALGOLOJİ BİLİM DALI"** | 165 (birebir aynı normalize ad) | ✅ birebir |
| kind_label: **24 değer**; Anabilim Dalı 36K, Bölüm 21.4K, ror_child 15K, Lisans 13.6K, Tezli YL 11.2K, Önlisans 9.4K, Bilim Dalı 7.5K, Doktora 6K, UYG-AR 4.1K, Fakülte 2.3K, MYO 1.1K | 24 değer; 36.066 / 21.421 / 14.957 / 13.596 / 11.150 / 9.375 / 7.486 / 6.033 / 4.088 / 2.284 / 1.104 | ✅ birebir |
| "Boş kind_label birebir inactive satırlara denk" | Aktiflerde boş: **0**; inaktif 40.808'in **hepsi** boş | ✅ birebir |
| **%98 düz ad, 2.802 zincirli aktif ad** | 2.802 virgüllü (%2.03), 135.496 düz (%97.97) | ✅ birebir |
| Inactive 40.808'in büyük kütlesi zincirli | 40.510/40.808 virgüllü (%99.3) | ✅ |
| ror_child **%10.8** | 14.957 aktif (%10.82) | ✅ birebir |
| **%81 paylaşılan ad** (112.149 satır) | 112.147 (%81.09) — 2 satırlık fark normalize detayı | ✅ |
| `iz`/`top_iz` fiilen boş (138K'da 4) | 4 / 4 | ✅ birebir |
| 4.340 parent'a bağlı düz hiyerarşi | 4.340 (tüm satırlarda; yalnız aktiflerde 4.235) | ✅ |

### 1.2 Düzeltilmesi gerekenler (rehber yanlış ya da yanıltıcı)

1. **"SBÜ (parent=49, 8.865 subunit)"** — 8.865 sayısı **aktif+inaktif toplam**.
   Aktif subunit sayısı **7.000**; duplicate-grup üyesi olan aktifler 6.534
   (EXPERIMENTS "Sorun 2" ile tutarlı). Duplicate bağlamında doğru sayı 7.000.
2. **"2.802 zincirli adın 966'sı üniversite adıyla başlıyor"** — **hiçbir makul
   kriterle yeniden üretemedim.** Ölçtüklerim: zincirli olup ilk segmenti kendi
   parent adıyla birebir eşleşen **134**; ilk segmenti herhangi bir parent
   adıyla eşleşen **170**; ilk segmentinde "üniversite" kelimesi geçen **106**.
   Virgül şartı kaldırılırsa: adı kendi parent adının ön eki olarak başlayan
   aktif subunit **704**; ilk 6 kelimesinde "üniversi" geçen **1.221**. Yani
   "parent-injection'ın parent adını iki kez soktuğu" küme gerçek ama boyutu
   kritere göre ~700–1.200; "zincirlilerin 966'sı" ifadesi bu haliyle yanlış.
   Sorunun kendisi (çift enjeksiyon) geçerli ama **aktiflerin ≤%0.9'u** —
   rehberdeki yerleşiminden daha küçük bir dert.
3. **"'bilgisayar teknolojileri bölümü' 404 üniversitede"** — 404 **kayıt**,
   ama **176 farklı üniversitede**. Paylaşılan-ad argümanını değiştirmez,
   ifade hatası.
4. (Küçük) "adı University ile biten 181 ror_child" → ben 189 ölçtüm
   (kriter farkı olabilir; büyüklük sırası aynı).

### 1.3 Tamamen bayatlamış olanlar

- **Bölüm 3 girişindeki eval bağlamı** ("parent top-1 %87, subunit %42"):
  güncel resmî sayılar (Faz 3.4 çift-seed doğrulaması, n=2250) parent top-1
  **0.8987 / 0.9013** (seed=42/7), subunit **0.4627 / 0.4640**, auto_match
  **491 ve 430 satırın %100'ü doğru**. Parent tarafı rehberin yazıldığı andan
  belirgin ileride.
- **"2250'nin 474'ü (%21) ambiguous"**: güncel seed=42 dağılımı ambiguous=**635**
  — duplicate mekanizması aynen duruyor (bkz. 2.2), sayı küçülmedi, büyüdü
  (auto_match hacmi arttıkça review havuzu küçüldü, ambiguous kaldı).
- **Bölüm 6'nın durum tespiti** ("yalnızca 3.1 bitti, 3.2–3.5 duruyor"):
  tamamen eski. Bugünkü HEAD'de **Faz 3.1–3.7'nin tamamı kapanmış**, 3.8
  (cross-encoder) bilinçli olarak açılmamış. Ayrıntı Bölüm 2'de.

Bir yan bulgu: **CLAUDE.md yine gerçeğin gerisinde** — hâlâ "tests altındaki
her dosya 0 bayt, hiç test yok" diyor; gerçekte **236 unit test** (+5
integration) var ve Faz 1'den beri her davranış değişikliği testle
kilitleniyor. Projenin "dokümantasyon gerçeklikten kopuyor" deseni (tasarim.md
atıfları → eski CLAUDE.md → şimdi yine CLAUDE.md) üçüncü kez tekrarlıyor.

---

## 2. Bölüm 6 kararının ("sıfırdan başlama, Faz 3'ü bitir") güncel durumla yeniden değerlendirilmesi

Rehberin kararı kendi anına göre doğruydu ve **büyük ölçüde uygulandı** — ama
önerilen üç adımın gerçekleşme biçimi rehberin öngördüğünden önemli ölçüde
farklı, ve bu fark v3 karar noktasının bugünkü anlamını değiştiriyor.

### 2.1 Adım 2 ("3.2+3.3'ü birlikte bitir"): YAPILDI — ve rehberin beklediğinin tersi sonuç verdi

- 3.2 mimari ayrımı yapıldı (weights_parent/weights_subunit).
- 3.3'te record_type'a göre **ayrı LR gerçekten eğitildi**, eşikle birlikte
  kalibre edildi, seed=42'de parlak göründü (auto_match +%37.8, iç doğruluk
  1.0000) — ve **held-out seed=7'de KRİTİK KISITI ihlal etti** (0.9855;
  IDA/ADA/IPM kısa-akronim çarpışmaları). Geri alındı.
- Rehberin önerdiği gerçek kalibrasyon (isotonic) da denendi: 0.90–0.94
  bandında eğri **tamamen düz** çıktı — çözünürlük yok, uygulanmadı.
  `calibrate_score` bugün hâlâ kimlik fonksiyonu (kodda doğruladım).

Yani rehberin 2.3 tezi ("elle ağırlık hiç olmasın, baştan öğrenilmiş+kalibre")
bu verinin/etiketin mevcut hâlinde **çürütüldü**: elle ayarlanmış, çeşitliliği
korunmuş ağırlık seti, öğrenilmiş-ama-kırpılmış setten held-out'ta daha
güvenli çıktı. (Nüans için bkz. 3.3.)

### 2.2 Adım 1 ("3.5'i öne çek: duplicate birleştir + kind_label"): KISMEN ve FARKLI yapıldı — ve rehberin ASIL önerisi hâlâ denenmedi

Burası bu retrospektifin en önemli tespiti:

- Denenen şey (Faz 3 başlangıcı + Faz 3.5), **kayıtları ES'te ayrı tutup
  margin hesabını klon-farkındalıklı yapmak** idi. Bu, near-tie ikizler
  arasında yazı-tura kaybettirdiği için (Çankırı "TASARIM BÖLÜMÜ" vakası)
  kritik kısıtı ihlal etti ve doğru şekilde geri alındı. Ardından 4 ayırt
  etme sinyali (canonical_ref, grup boyu, skor farkı, embedding mesafesi)
  tek tek test edilip hepsi aynı yapısal nedenle elendi: **grup üyeleri
  arasında ayırt edici hiçbir alan yok.** Faz 3.5 "kod tarafında çözülemez"
  diye kapatıldı.
- Ama rehberin 3.1'de önerdiği şey bu değildi: **ingest'te grubu TEK kayda
  indirmek, birleşen id'leri kayıtta liste olarak taşımak.** Bu yol hiç
  denenmedi. Ve Faz 3.5'in imkânsızlık kanıtı bu yolu zayıflatmaz —
  **güçlendirir**: madem üyeler hiçbir gözlemlenebilir alanda ayırt
  edilemiyor, onları ayrı kayıtlar olarak yarıştırmak zaten yanlış; near-tie
  yazı-turası ancak iki ayrı kayıt yarışırsa var olur. Tek birleşik kayıt
  ikizine kaybedemez. Bedeli dürüsttür: o gruplar için sistemin çıktısı tek
  id değil id listesidir — ki verinin gerçek çözünürlüğü de tam olarak bu.
  (Eval tarafında "expected_id ∈ birleşik-id-listesi" doğru sayılır;
  downstream tüketici tek id istiyorsa bu bir ürün kararıdır, skorlama
  sorunu değil.)
- **kind_label bugün hâlâ ölü kolon** (grep: `src/` içinde tek kullanım
  `ingest/schema.py:113`, mapping/index/rerank'e gitmiyor) — rehberin
  "en yüksek getiri adayı" dediği iş Faz 2B.3 reindex'ine de, Faz 3'e de
  hiç girmedi. Not: o bölümün beklediği kazanımın bir kısmını Ö11 (ingest
  qualifier çıkarımı, subunit top-1 +3.66pp) fiilen teslim etti; kalan
  değeri artık ölçmeden varsaymamak gerekir.

### 2.3 Adım 3 ("v3 karar noktası = Faz 3 regresyon kapısı"): KAPIYA GELİNDİ — ama kapının kendi koşulu eksik

Rehber v3 kararını "Faz 3 sonunda, kalibre lineer sistemin **gerçek sette
ölçülmüş** kesinlik/hacmiyle" veriyordu. Faz 3 bitti; ölçülen tavan:

- Sentetik (n=2250): genel top-1 0.608, parent 0.899, subunit 0.463;
  auto_match 491 (%21.8) — iç doğruluk %100, **iki seed'de birden**.
- Gerçek 1806 satır: parent auto_match 307 (%17), subunit 29 (%1.6);
  parent review hâlâ 1231 (%68).

Ama **ACTION_PLAN 2A.4 (elle etiketlenmiş gerçek set) hiç tamamlanmadı** —
`inres label-set` aracı yazıldı, etiketleme yapılmadı. Yani Faz 3'ün tüm
kabul kapıları sentetik gold + seed=7 ile geçildi; "gerçek sette auto_match
kesinliği ≥ %99" (ACTION_PLAN Faz 3 kapısının (a) maddesi) **hiç ölçülmedi**.
Rehberin kendi mantığıyla bile v3 kararı bugün verilemez: karar için gereken
ölçüm zemini henüz yok. Benim cevabım Bölüm 5'te.

---

## 3. Rehberin mimari önerileri — sonraki bulguların ışığında tek tek

| Öneri | Bugünkü hüküm | Kanıt |
|---|---|---|
| **2.1 ES'siz tek süreç** (bm25s/tantivy + FAISS) | Hâlâ savunulabilir ama **gerekçesi zayıfladı**. Rehberin "tanım gereği yok eder" dediği iki hata sınıfının faturası v2'de çoktan ödendi: ham skorlar 3.1'de retrofit edildi (+%15.8 auto_match, sıfır kayıp), determinizm 2A.1'de kalıcı çözüldü (force-merge + id sort, `run_indexing`e gömülü), `_source` %95 küçüldü, arama paralellendi (0.42s/sorgu). Kalan gerçek maliyet: analyzer/normalize çift-implementasyonu (artık test-kilitli) ve operasyonel ağırlık. Tek süreç ancak v3 gerçekten açılırsa doğru; v2'ye geriye dönük uygulanacak bir şey değil. | EXPERIMENTS Faz 3.1, 2A.1, K3, 3.7 |
| **2.2 RRF sadece havuzlama, ham skorlar gün-1 özellik** | **GÜÇLENDİ** — 3.1 tam bunu yaptı ve tek başına en temiz kazanımlardan birini verdi (auto_match 425→492, iç doğruluk 1.0 sabit). Rehber haklıydı; v3'te gün-1 kuralı olmalı. | Faz 3.1 tablosu |
| **2.2 Tek index / tek korpus IDF** | Kısmen aşıldı: KTÜ/IDF vakası `strip_subunit_only_terms` ile hedefli çözüldü ("ankara üniversitesi tıp fakültesi" → doğru). Yapısal argüman v3 için hâlâ doğru, ama v2'deki pratik acı büyük ölçüde dindi. | Faz 2B.2 |
| **2.3 Baştan öğrenilmiş + kalibre karar katmanı** | **ÇÜRÜDÜ (güçlü formunda)**. Ayrı-LR denemesi held-out'ta sistematik zaaf üretti; kök neden öğrenmenin kendisi değil, **konveks+negatif-kırpma formülasyonunun sinyal çeşitliliğini yok etmesi** (es_lexical→0 = kısa-akronim sigortasının iptali). İsotonic de mevcut skor kümelenmesinde çözünürlüksüz. Ders: "öğrenilmiş" ancak (a) gerçek etiketlerle, (b) taban-ağırlık kısıtıyla / karışım (elle⊕öğrenilmiş) ile, (c) iki-seed kapısıyla denenebilir. "Elle ağırlık hiç olmasın" bugünkü kanıtla yanlış. | Faz 3.3, Adım 6; config yorumları |
| **2.4 Gerçek veri etiketleme = 1. hafta işi** | **GÜÇLENDİ ve hâlâ yapılmadı** — v2'nin en büyük açık borcu (bkz. 2.3, 5.1). | Faz 2 sonu notu |
| **2.5 Korkuluklar** (testler, pydantic forbid, tasarım dokümanı repoda) | Testler kısmı fazlasıyla doğrulandı (K2 (YL) bug'ı tek assert'le ilk gün yakalanırdı; bugün 236 test var). Config ölü-anahtar temizliği yapıldı (1D.5) ama `extra="forbid"` hâlâ yok. tasarim.md hâlâ kayıp. | Faz 1; bu oturum |
| **2.6 Review bandı için LLM hakemi** | **Hiç denenmedi; bugün muhtemelen en yüksek kaldıraçlı açık fikir.** Gerçek veride parent kararlarının %68'i hâlâ review; lineer sistemin kanıtlanmış-çözemediği sınıfların bir kısmı (Ticaret↔Commerce çeviri çifti, "kurum değil" gri bandı, KTU çok-ülke belirsizliği) tam olarak bir hakem-LLM'in güçlü olduğu yerler. Klon grupları ise LLM'e de kapalı (ayırt edici bilgi metinde yok — 3.5 kanıtı hakem için de geçerli; hakemden beklenti oraya kurulmamalı). | Faz 2 sonu gerçek-veri tablosu; Takip 1 |
| **Bölüm 4 iki-ad-konvansiyonu şeması** | Yön doğru, aciliyet rehberdekinden düşük: çift-enjeksiyon kümesi ölçümümde ~700–1.200 kayıt (≤%0.9). v3 şeması için doğru tasarım; v2'de tek başına reindex'i hak etmez, ancak başka bir reindex turuna binerse yapılır. | Bu oturum ölçümleri |

---

## 4. Sıfırdan yapsaydım nasıl yapardım — kendi taslağım

Rehberin F0–F5 planına büyük ölçüde katılıyorum; farklarım şunlar:

1. **Gün-0 işi kod değil, korpus profili.** Bu projenin en pahalı sürprizlerinin
   tamamı (13.557 klon satırı, %81 paylaşılan ad, self-parent 44, iki-ad
   konvansiyonu, akronim çarpışmaları, boş iz/top_iz) **retrieval kodu
   yazılmadan önce 10'ar satırlık groupby sorgularıyla görülebilirdi.**
   "İlk hafta etiketleme"nin (rehber 2.4) yanına: ilk gün join-anahtarı
   profili — `(parent_id, normalized_name)` kardinalitesi, ad-paylaşım
   histogramı, alan doluluk matrisi — ve bu profil quality_report'un kalıcı,
   her ingest'te yeniden üretilen parçası olur.
2. **Çıktı tipi baştan "id listesi + güven" olurdu, tek id değil.** Verinin
   gerçek çözünürlüğü bazı sınıflar için tek kayıt değil (klon grupları,
   parent'sız bölüm adları). Tek-id çıktı varsayımı, auto_match_margin'in
   klonlarda matematiksel imkânsızlığa dönüşmesinin asıl kaynağı. Klonlar
   ingest'te birleşir (id listesi korunur); parent'sız subunit sorgusu için
   hedef metrik baştan "parent-koşullu top-1" olur (rehber 3.5'e katılıyorum).
3. **Karar katmanı: elle-init edilen, tabanlı-kısıtlı öğrenme.** Sinyal
   çeşitliliği bir güvenlik özelliği (Faz 3.3'ün ana dersi) — öğrenici hangi
   formda olursa olsun hiçbir sinyali sıfıra kırpamaz (min ağırlık tabanı ya
   da elle⊕öğrenilmiş karışım). Eşikler record_type başına ayrı (3.3'te
   ölçülen maliyet: paylaşılan eşik yüzünden subunit hacminin %12'si parent'a
   feda edildi). Kalibrasyon ancak gerçek etiketli set n≥1000 olunca.
4. **Retrieval: tek korpus + `record_type` filtresi, ham BM25+cosine gün-1
   özellik, RRF yalnız havuzlama.** (Rehber 2.2 aynen.) ES vs tek-süreç
   seçimini ideolojik görmüyorum: ekip ES işletmeye alışkınsa ES'te kalınır
   ama force-merge/determinizm ve skor-taşıma kuralları gün-1 şablona gömülür
   — v2'nin bu dersleri artık maliyetsiz kopyalanabilir.
5. **Eval: 3 katman.** (i) ~50 sorguluk sabit CI fikstürü (saniyeler),
   (ii) sentetik gold+noise (ayar), (iii) gerçek etiketli set (kabul; auto
   kesinliği + "kurum değil" yakalama YALNIZ burada raporlanır). Sentetik
   setin auto_match kesinliği raporlarda "iç doğruluk (sentetik)" diye
   etiketlenir — %100'ün yönetime "gerçek kesinlik" gibi taşınmasını
   yapısal olarak engellemek için.
6. **Review bandına LLM hakemi F5'te değil F4'te** — çünkü gerçek verinin
   karar kütlesi orada yaşıyor (%68 review) ve hakem, etiketleme işinin
   kendisini de hızlandırır (ön-etiket + insan onayı).

Bunun dışında v2'nin kanıtlanmış kazanımları aynen taşınır: tüm-alias embed +
parent-injection, qualifier sert kuralları rerank'te, sorgu+belge simetrisi,
EXPERIMENTS disiplini, iki-seed metodolojisi.

---

## 5. "Şimdi ne yapmalı" — güncel duruma göre benim cevabım

Rehberin cevabı ("Faz 3'ü bitir") tüketildi; kapı koşulu eksik olduğu için
"v3'e geç/geçme" kararı da henüz verilemez. Sıram:

1. **Gerçek etiketli set (2A.4) — başka her şeyden önce.** 300–500 satır,
   `data/inbox` örnekleminden, "doğru parent id / doğru subunit id (veya
   grup) / kurum değil / belirsiz" etiketleriyle. Araç (`inres label-set`)
   hazır; darboğaz insan-saati. Bu olmadan: auto_match'in gerçek kesinliği
   bilinmiyor (sentetik %100'ün gerçekte kaç olduğu belirsiz), LLM-hakem ve
   kalibrasyon ölçülemez, v3 kapısı açılamaz. Etiketleme sırasında LLM
   ön-etiketi + insan onayı kullanılabilir (maliyeti ~3-5x düşürür).
2. **Klon gruplarını ingest'te birleştir (rehber 3.1'in GERÇEK önerisi —
   hâlâ denenmemiş).** Alias'larına kadar özdeş `(parent_id, normalized_name,
   kind_label)` gruplarını tek kanonik kayda indir, `merged_ids` listesi
   kayıtta kalsın; eval "expected ∈ merged_ids"i doğru saysın. Faz 3.5'in
   kapattığı şey "ayırt etme" sınıfıydı; "birleştirme" o kanıtın doğal
   sonucudur ve near-tie yazı-turası riskini tanım gereği taşımaz. Beklenen
   etki: 13.557 satırlık margin-eritici kütle ve ambiguous bandının (635/2250)
   önemli kısmı. Reindex gerektirdiği için **kind_label'ın index'e taşınması
   ve (ucuzsa) zincirli-ad ilk-segment tekilleştirmesi aynı tura** biner.
   Kabul: iki seed + (1'den gelen) gerçek set; auto_match iç doğruluk tabanı
   %100/%100.
3. **LLM hakem POC'u review bandında** (yalnız review; auto_match'e
   dokunmaz). Ölçüm 1'deki gerçek set üzerinde: review→auto terfilerinin
   kesinliği, review→no_match tenzillerinin isabeti. Hedef gerçek veride
   parent review %68'ini anlamlı küçültmek.
4. **Eşikleri record_type'a ayır** (auto_match_score/margin parent ve subunit
   için ayrı) — 3.3'ün belgelediği paylaşılan-eşik maliyetini geri kazanmak
   için; 2'nin reindex'inden bağımsız, ucuz bir kalibrasyon turu.
5. **v3'e sıfırdan geçiş: hâlâ HAYIR.** Kalan hata sınıflarının hiçbiri
   (klonlar, paylaşılan adlar, kısa-akronim çok-anlamlılığı, çeviri çiftleri)
   ES→tantivy/FAISS taşınmasıyla çözülmez — bunlar veri ve çıktı-tipi
   sorunları. v3 ancak 1–3 bittikten sonra, gerçek sette ölçülmüş tavan hâlâ
   iş hedefinin altındaysa ve o açığın kaynağı gerçekten mimariyse açılır.
   (O gün gelirse rehberin Bölüm 2 + Bölüm 4 taslağı, buradaki 4. bölümle
   birlikte hâlâ iyi bir başlangıçtır.)

---

## 6. Kod tabanında hâlâ sorgulanmamış varsayımlar

1. **`candidates_per_pool=150` hiç sweep edilmedi** — rank-tabanlı sinyaller
   havuz boyuna duyarlı; 150 F2'den beri veri-kanıtsız duruyor.
2. **`review_score=0.60` F4'ten beri yeniden kalibre edilmedi** — floor-kapısı
   ve 8-sinyal geçişi skor dağılımını değiştirdi; alt eşik hiç yeniden
   ölçülmedi.
3. **`subunit_specific_match` (0.05) her LR koşusunda negatif katsayı aldı**
   (tek-LR −2.86; 3.3'te her iki modelde 0'a kırpıldı) ama config'te hâlâ
   pozitif ağırlıkla duruyor — İ2 hiçbir zaman nihai karara bağlanmadı.
4. **Eşikler record_type-paylaşımlı** (bkz. 5.4) — 3.3'te maliyeti ölçüldü,
   düzeltilmedi.
5. **Gold set hâlâ DB'nin kendi alias'larından üretiliyor** — K5 seed
   ayrımıyla overfit riski yönetildi ama döngüsellik/temsil sorunu duruyor;
   "sentetik %100 iç doğruluk" iddiasının dış geçerliliği ölçülmemiş durumda.
6. **`calibrate_score` kimlik** — skor bir olasılık değil; 0.92 eşiği yalnız
   bugünkü ağırlık vektörü için anlamlı (isotonic denemesi çözünürlüksüzdü,
   ama bu n=600'lük tek denemeydi; gerçek etiketlerle yeniden denenmedi).
7. **Parent/subunit ayrı index'lerin IDF çarpıklığı** yalnız hedefli kelime
   listesiyle (`strip_subunit_only_terms`, 5 kelime) yamalı — listede olmayan
   bir jenerik kelime (ör. "enstitüsü" bilinçli dışarıda) aynı mekanizmayı
   yeniden üretebilir.
8. **Faz 3.7 doğrulamasındaki "493K parent + 455K subunit dolu index" notu**
   belge sayılarıyla (106K/138K) çelişiyor — muhtemelen nested alias
   Lucene-doc sayısı; zararsız ama EXPERIMENTS'te açıklamasız duran tek
   tutarsız sayı.

---

## 7. Süreç değerlendirmesi — neresi verimliydi, nerede kayıp oldu

**İyi işleyen:** hipotez→ölçüm→karar günlüğü; kritik kısıtın (auto_match iç
doğruluğu) her turda ayrı doğrulanması; ve özellikle **dürüst geri-alma**:
üç büyük deney (v2.1 tek-LR, Sorun 2 klon-margin, Faz 3.3 ayrı-LR) üçü de
gerekçeli geri alındı ve üçünde de altyapı + bilgi kaldı. seed=7 held-out
kuralı tam olarak tasarlandığı işi yaptı: 3.3'ün seed=42'de görünmez olan
sistematik zaafını üretime girmeden yakaladı. Bu, projenin en değerli
süreç-varlığı.

**Kayıplar / geç kalınanlar:**
1. **Determinizm (Ö8) geç çözüldü.** ±1pp kararlar alınan ilk ~10 tur,
   sonradan 4/1806 → "City of Antwerp" flip-flop'u → taban 0.9903'ün kısmen
   şans eseri olduğunun anlaşılmasıyla (gerçek taban 0.9804) kısmen kayan bir
   zeminde koşuldu. 2A.1 ilk hafta yapılsaydı en az 2–3 yeniden-kalibrasyon
   turu ve "0.92 eşiği" tartışmasının bir kısmı gereksizleşirdi.
2. **Testler 14 commit geç geldi** — (YL) bug'ı bunun belgelenmiş faturası;
   rehber 2.5 ve REVIEW K1 haklıydı.
3. **Gerçek etiketli set hâlâ yok** — planın (2A.4) en eski, en çok ertelenen
   maddesi; her fazın kabulü "sentetik + seed=7" ile yapıldı. Bugün itibarıyla
   projenin bir numaralı borcu.
4. Görece küçük: qualifier ağırlığı 0.06 kararı üç kez yeniden ölçüldü
   (orijinal, 1B.3, 3.4) ve üçünde de aynı yerde kaldı — K2 bağımlılığı
   nedeniyle ilk ikisi kaçınılmazdı; 3.4 turu güvence değeri taşısa da yeni
   bilgi üretmedi.

---

## 8. En kritik içgörüler

1. **Faz 3.5'in imkânsızlık kanıtı yanlış anlaşılmaya açık:** kapattığı şey
   "klonları AYIRT etme" yaklaşım sınıfı; rehberin asıl önerisi olan
   "ingest'te BİRLEŞTİRME + id listesi" denenmedi ve o kanıt tarafından
   güçlendiriliyor. Kod tarafında hâlâ açık, muhtemelen en büyük tek kazanım.
2. **Sinyal çeşitliliği bir doğruluk hilesi değil, güvenlik özelliği.**
   es_lexical'in IDF cezası, kısa-akronim çarpışmalarına karşı sistemin
   sigortasıydı; LR onu "marjinal katkısız" diye kırptığında seed=42 bunu
   göstermedi, seed=7 gösterdi. Gelecekteki her öğrenme denemesi taban-ağırlık
   kısıtıyla yapılmalı.
3. **Sentetik %100 iç doğruluk ≠ gerçek kesinlik.** Gerçek transfer zaten bir
   kez ölçüldü (gold auto %18 iken gerçek parent auto %5'ti, Faz 2B sonrası
   %17). Gerçek etiketli set gelmeden auto_match kesinliği hakkında dışa
   dönük hiçbir iddia taşınmamalı.
4. **Kalan hataların ağırlık merkezi veri, mimari değil** — klonlar (bilgi
   kaynakta yok), %81 paylaşılan ad (parent'sız sorgu tanım gereği belirsiz),
   kısa akronimler (KTU=4 gerçek kurum), çeviri çiftleri. Bunların hiçbirini
   ne yeni bir arama motoru ne cross-encoder çözer; çözüm çıktı-tipi (id
   listesi), bağlam-koşullu metrik ve hakem/insan triyajı.
5. **Rehberin veri taraması güvenilir, durum/karar bölümü bayat.** Sayısal
   iddiaların ~%85'i birebir doğrulandı; iki ifade düzeltildi (SBÜ 8.865→
   aktif 7.000; "966" yeniden üretilemedi, gerçek küme ~700–1.200). Bölüm 6
   ise Faz 3'ün tamamlanmasıyla tarihsel belge hâline geldi.
6. **ES'ten çıkma gerekçesi zamanla eridi** — rehberin saydığı maliyetlerin
   çoğu v2 içinde tek tek ödendi (ham skor retrofit'i, determinizm,
   _source, paralellik). "Tek süreç" argümanı v3 için hâlâ geçerli ama artık
   "hata sınıflarını yok eder" değil "operasyonel sadeleştirir" gücünde.
7. **Parent tarafı fiilen çözülmüş durumda** (top-1 ~0.90, auto %100 iki
   seed'de, gerçek veride %17 hacim); ilerlemenin tamamı subunit tarafında
   ve orası veri-sınırlı. Kaynak ayrımı buna göre yapılmalı.
8. **Dokümantasyon çürümesi üçüncü kez tekrarlıyor** (tasarim.md → eski
   CLAUDE.md → şimdiki CLAUDE.md'nin "test yok" iddiası). 15 dakikalık
   CLAUDE.md güncellemesi yine en yüksek kaldıraçlı hijyen işi.
