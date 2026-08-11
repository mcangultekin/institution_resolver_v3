# Envanter CSV'si için özel mod — analiz, kararlar ve uygulama

*Tarih: 2026-08-11. Konu: `institution-field-inventory.csv` (8.920.512 satır) için
sistemin nasıl konumlandırılacağı; ölçümler, düzeltilen iddialar, kurulan veri
setleri ve yazılan `jobs/inventory` modu.*

---

## 0. Bu oturumun özeti

Başlangıç sorusu "sistemi bu CSV'ye göre optimize edelim" idi. Analiz sırasında
işin tanımı iki kez değişti, çünkü iki varsayım ölçünce yanlış çıktı:

1. Bedava kapatılabilecek satır payı **%82 değil %76,3** (§2.3).
2. Sistemin çıktısı bu CSV'nin `parent_id` sütununa **yazılamıyor** — id uzayları
   farklı (§3). Bu, teslim tanımını "mevcut sütunları doldur"dan "yeni sütun
   ekle"ye çevirdi (§4).

Sonuçta: iki veri seti üretildi (§5), 500 gerçek sorguda ölçüm yapıldı (§6),
embedding maliyeti profillendi (§7) ve işe özel bir mod yazılıp doğrulandı (§8–§10).

---

## 1. Amaç

`institution-field-inventory.csv`, üretimdeki her kaydın (yazar, hakem,
kullanıcı, başvuru…) hangi kuruma bağlı olduğunu satır satır taşıyor. Amaç:
**parent'ı boş olan satırlar için bizim sistemimizin ürettiği parent (ve
mümkünse subunit) kararını yazmak.** Subunit baştan "opsiyonel" olarak
konumlandırıldı.

| | satır | pay |
|---|---:|---:|
| parent'ı dolu | 4.596.039 | %51,5 |
| **parent'ı boş — işlenecek** | **4.324.473** | **%48,5** |
| toplam | 8.920.512 | %100 |

---

## 2. Veri keşfi

### 2.1 Dosyanın dolu kısmı nasıl doldu

İsim eşleştirmeyle değil. Katalogun (`data/raw/institution_parent.csv`)
`legacy_institution_ids` sütunu üzerinden **deterministik bir id join'iyle**:
ilk 400.000 satırda dolu olan 200.157 satırın *tamamı* ve yalnızca onlar bu
listede çıkıyor (%100 örtüşme). Yani "dolu" satırlar bir çözümleme çıktısı değil,
bir eşleme tablosunun izdüşümü.

Yan sonuç: `current_institution_id` → parent eşlemesi dosya genelinde çelişkisiz
(1.144.364 benzersiz id'nin hiçbirinde çoklu parent yok, kısmen dolu id yok).

### 2.2 Tekilleştirme

4.324.473 boş satır, çok daha az benzersiz isme iniyor:

```
4.324.473 satır
   → 376.541 benzersiz ham ad
   → 301.521 benzersiz normalize ad     (%20 daha az sorgu)
```

Normalize anahtarı seçildi; sorgu metni olarak grubun **en sık ham varyantı**
taşınıyor (virgül gibi sınır sinyalleri normalize edilirken siliniyor, bkz. §7.2).

### 2.3 "%82" iddiası — test edildi, düzeltildi

İlk analizde dört kaldıraçla dosyanın %51,5 → ~%82'sinin modelsiz dolacağı
söylenmişti. Tam tarama ile test edildi:

| kaldıraç | satır | kümülatif |
|---|---:|---:|
| zaten dolu | 4.596.039 | %51,5 |
| **A — ad-join** (aynı ad dosyanın başka yerinde çözülmüş) | +2.206.663 | **%76,3** |
| B/C/D — katalogla birebir eşleşme | **+2.028** | %76,3 |

**A tuttu, B/C/D çöktü.** Sebebi §3.

A'nın dayanağı sağlam: 14.607 ortak addan yalnız **16'sında** (4.675 satır)
çelişen parent var (%99,9 tutarlı). Mekanizma: aynı kurum kaynak veride birden
çok id'yle kayıtlı; bazı id'ler katalogun legacy listesinde var, bazıları yok.
Örnek: `gazi universitesi` adlı 77.627 satırın 47.437'si dolu, 30.190'ı boş.

---

## 3. Kritik bulgu: id uzayı uyuşmazlığı

CSV'nin `parent_id` sütunu **bizim katalogumuzun id uzayında değil.**

| ölçüm | sonuç |
|---|---:|
| katalog parent kaydı → CSV `parent_id` köprüsü kurulabilen | **338 / 106.331 (%0,3)** |
| tüm dosyada benzersiz `parent_id` | **338** |
| tüm dosyada benzersiz `subunit_id` | 67.446 |
| `iz` kolonu köprü mü | hayır — 106.331 katalog kaydının yalnız 397'sinde var |
| `canonical_ref` köprü mü | hayır — 105.941'i `ror:`, yalnız 350'si `yok:` |

Yani bu dosyanın hedef parent sözlüğü 106.183 kayıtlık katalog değil, **338
kurumluk kapalı bir liste** (Türkiye yükseköğretim kurumları). Sistem bir adı
doğru çözse bile sonucu eski sütuna yazamıyor.

Kontrol amaçlı ölçüm: 338'lik sözlüğe basit **ifade-içi geçiş** kuralıyla
bakıldığında dosya %81,3'e çıkıyor, ama kesinlik **%97,15** (48.143 dolu ad gold;
kural 34.998'ine cevap verdi, 997 yanlış) — projenin %98 `auto_match` hedefinin
altında. Yanlışların çoğu sözlüğün kendi ikizleri: `Kayseri University` /
`KAYSERİ ÜNİVERSİTESİ`, `VAN YUZUNCU YIL UNIVERSITY` / `YÜZÜNCÜ YIL ÜNİVERSİTESİ`.

> **Hafızaya alındı:** `csv_id_uzayi_uyusmazligi.md`

---

## 4. Teslim tanımının netleşmesi (kullanıcı kararı)

> "parent ve subunit için **sütun ekleyeceğiz**; parent'i boş olanların yaptığımız
> parent ve subuniti oraya yazacağız."

Bu, id uzayı sorununu ortadan kaldırdı: çıktı **yeni sütunlara**, kendi katalog
uzayımızda yazılacak. Köprüye gerek yok.

Ama bir yan sonucu var: **A kaldıracı (ad-join) yeni sütunlar için geçerli değil.**
O, dosyanın *eski* sütunlarını dolduruyordu. Yeni sütunlar bizim uzayımızda
olacağı için o 14.591 adın da batch'ten geçmesi gerekirdi. Kullanıcı kararı:
onlara güvenip işleme setinden çıkar, ayrı dosyada sakla (§5).

---

## 5. Üretilen veri setleri

Her ikisi de `data/jobs/` altında (gitignore kapsamında). Orijinal CSV'ye
**dokunulmadı**.

### 5.1 `batch_input_parent_empty.csv` — işlenecek set

| | |
|---|---:|
| benzersiz sorgu | **286.948** |
| temsil ettiği satır | 2.117.810 |
| boyut | 44 MB |

Kolonlar: `query` (grubun en sık ham varyantı), `normalized_name` (geri-join
anahtarı), `rows`, `raw_variants`, `source_ids`, `top_object_class`,
`legacy_conflict`.

Çelişkili eski cevaba sahip 16 ad bilerek burada bırakıldı — kararı sistem versin.

**Hacim eğrisi** (öncelik sırası hazır):

| ilk N sorgu | açtığı satır |
|---:|---:|
| 1.000 | %28,7 |
| 10.000 | %56,3 |
| 20.000 | %65,4 |
| 50.000 | %77,6 |

### 5.2 `trusted_legacy_answers.csv` — güvenilen, sonra işlenecek set

| | |
|---|---:|
| ad | **14.591** |
| temsil ettiği satır | 2.206.663 |
| boyut | 4,7 MB |

| subunit durumu | ad | kullanım |
|---|---:|---|
| tekil | 11.056 | parent + subunit (336.653 satır) |
| çoklu | 2.995 | **yalnız parent'a güven** |
| yok | 540 | dolu kardeşlerinde subunit hiç yok |

`filled_rows_evidence` kolonu, cevabın kaç dolu satıra dayandığını taşır
(Gazi'de 47.437, Pamukkale'de 14.111) — zayıf dayanaklılar birleştirmeden önce
süzülebilir.

> **Açık karar:** bu 14.591 ad eski (338'lik) uzayda, kalanlar katalog uzayında.
> Birleştirmede bu satırlara `source=legacy` bayrağı konmalı; yoksa yeni sütunlar
> iki farklı id uzayını karışık taşır.

---

## 6. 500 sorguluk ölçüm

`seed=42` ile `batch_input_parent_empty.csv`'den rastgele 500 sorgu
(`data/jobs/sample_500_2026-08-11.csv`), LLM yok.

| parent | adet | | subunit | adet |
|---|---:|---|---|---:|
| `auto_match` | 217 (%43,4) | | `auto_match` | 72 |
| `review` | 213 (%42,6) | | `review` | 301 |
| `ambiguous` | 47 (%9,4) | | `no_match` | 63 |
| `no_match` | 23 (%4,6) | | `ambiguous` | 21 |
| | | | (birim ifadesi yok) | 43 |

**Hakem yükü — "subunit opsiyonel"in ölçülmüş bedeli:**

| kapsam | LLM hakeme düşen |
|---|---:|
| parent **+** subunit (bugünkü `decide()`) | %78,4 |
| yalnız parent | **%52,0** |

Subunit'i tetikleyici olmaktan çıkarmak hakem çağrılarının üçte birini eliyor.

**Temel varsayım bozuldu:** eski ölçümde hakeme düşen pay %58'di, bu sette %78,4.
Kolay kütle `trusted` dosyasına ayrıldığı için kalan set gerçekten zorlaştı.

### 6.1 Kalite bulguları (çözülmedi, kayda geçti)

**Genel adlı katalog kayıtları çekim merkezi oluyor** — `conf=1.000` ile:

```
Yalvaç State Hospital, Department of Cardiovascular Surgery -> "State Hospital"
St. Georges University School of Medicine                   -> "University School"
```

Bunlar `auto_match`, yani insan görmeden veriye karışır. Örneklemde 217
auto_match içinde ~2 tane; ama bu kayıtlar *çekim merkezi* olduğu için tüm sette
payları daha yüksek olabilir. `coklu_kurum_kaydi_defekti` ile aynı aile.

**Çok-kurumlu sorgu:** `Babes-Bolyai University & Óbuda University` →
`Obuda University`, auto_match. İkisinden birini sessizce seçiyor.

`no_match` tarafı sağlıklı: hukuk büroları, ilkokullar, `T.B.M.M. Milletvekili`.

---

## 7. Performans profili

### 7.1 Embedding

| | |
|---|---:|
| toplam | 357 ms/sorgu |
| **kodlama** | **103 ms/sorgu → %28,8** |
| kodlama çağrısı | 4,9 /sorgu (3,5'i cache MISS) |

Her sorgu yerel olarak kodlanıyor (`search_knn` → `encode_query` →
sentence-transformers). Sorgu başına ~3,5 **ayrı** transformer geçişi var:
tam sorgu + `decompose`'un seçtiği hipotez parçaları.

Batch boyutuna göre (M4, 256 metin):

| batch | ms/metin |
|---:|---:|
| 1 (bugünkü) | 18,94 |
| 4 | 10,12 |
| **8** | **5,25** |
| 32 | 5,08 |
| 128 | 5,82 |

**Değerlendirilen seçenekler:**

| | kazanç | depolama | karar |
|---|---:|---|---|
| (a) tam sorgu embedding'ini önden hesapla, CSV'ye/dosyaya koy | −29 ms | 860 MB | **reddedildi** |
| **(b) sorgu-içi batch'leme** | **−48 ms** | yok | **yapıldı** |
| (c) sorgular arası batch (16 sorgu → tek batch) | −80 ms | yok | ertelendi |

(a) reddedildi çünkü kodlamaların yalnız **%29'unu** kapsıyor: kalan ~2,5 metin,
`decompose`'un BM25 araması *sonrasında* seçilen hipotez parçaları — sorgu
metnine bakarak önceden bilinemiyorlar. Tüm olası span'ları önden kodlamak
sorgu başına O(n²) parça demek. Ayrıca CSV sütunu olarak saklamak uygun değil:
768 boyut × float32 = 3 KB/vektör, base64'le ~4 KB → 44 MB'lik girdi ~1,2 GB'a çıkar.

**Bağlam — bu kazançların yeri:** tam koşuda (yalnız parent + hakem) süre ~41
gün, bunun içinde embedding ~8 saat (%0,8). Yani en iyi embedding optimizasyonu
bile toplamı %0,7 kısaltır. Anlamlı olduğu yer **gate-only koşu**: 31 saat → 27 saat.
Süreyi belirleyen şey hakem: sorguların %52'si × 23,9 sn.

### 7.2 Normalizasyon katmanı — öneri ölçülüp reddedildi

"CSV'de zaten normalize sütunu var, girdideki normalize katmanı fazla" önerisi
test edildi:

- `expand_query_text` maliyeti: **0,017 ms/sorgu** (toplam sürenin on binde biri).
  Kaldırılacak maliyet yok.
- O katman CSV'nin `normalized_name`'inin kopyası **değil**: kısaltma açıyor ama
  case/aksanı bilerek koruyor (belge tarafı da doğal metinle gömüldüğü için
  simetri şart). CSV'nin formu virgülleri, aksanı ve büyük harfi siliyor.

A/B (120 sorgu, aynı oturum, gate-only):

| | |
|---|---:|
| aynı karar etiketi | 113/120 (%94,2) |
| aynı eşleşen kayıt | 117/120 (%97,5) |
| hız | 354 → 330 ms (%7) |

Yani temizlik değil, **davranış değişikliği**: %7 hız için %6 karar kayması.
Karar: girdi ham kalsın.

---

## 8. Mod tasarımı — alınan kararlar

`src/institution_resolver_v3/jobs/inventory.py`. Çekirdeği (retrieve/gate/judge)
import eder, **hiçbirini değiştirmez.**

| karar | seçim | gerekçe |
|---|---|---|
| subunit hakemi tetiklesin mi | **hayır** | hakem yükü %78,4 → %52,0 |
| hakem zaten çalıştıysa subunit cevabı | **kullanılır**, `decided_by=judge` | kural "subunit İÇİN LLM'e gitme"ydi; `judge()` ikisine birlikte karar verdiği için cevap bedava geliyor |
| auto_match olmayan taraf | **etiket + en iyi aday kaydedilir** | kuyruk/ikinci tur için veri kaybolmasın |
| hakem açık/kapalı | **`--judge/--no-judge` bayrağı** | önce gate-only tam koşu, sonra kalanlara hakem turu |
| sorgu-içi toplu kodlama | **modda açık, çekirdekte kapalı** | vektörler batch'te ~3e-07 sapıyor; normal akış bozulmasın |

---

## 9. Yapılan kod değişiklikleri

| dosya | değişiklik |
|---|---|
| `embedding/query_encoder.py` | `prewarm(texts)` + `_prepare()` eklendi; `_encode_prepared` önce tampona bakıyor. **Varsayılan akışta tampon hep boş** — kimse `prewarm` çağırmazsa davranış birebir eski. |
| `retrieve/resolve.py` | `encode_prewarm: bool = False` parametresi; `decompose`'dan sonra hipotez parçaları + tam sorgu tek batch'te kodlanıyor. **Varsayılan kapalı.** |
| `jobs/__init__.py`, `jobs/inventory.py` | **yeni** — modun kendisi. |
| `cli/main.py` | **yeni komut** `inventory-batch` (`--judge/--no-judge`, `--resume`, `--limit`, `--top`, `--model`). |

Kullanım:

```bash
# gate-only tam koşu (~27 saat)
python -m institution_resolver_v3.cli.main inventory-batch \
    data/jobs/batch_input_parent_empty.csv --no-judge \
    --out data/jobs/inventory_sonuc.csv --resume

# hakemli
python -m institution_resolver_v3.cli.main inventory-batch \
    data/jobs/batch_input_parent_empty.csv \
    --out data/jobs/inventory_sonuc.csv --resume
```

### 9.1 Çıktı şeması

Karar kolonları (`parent_id`, `subunit_id`…) ile aday kolonları
(`*_cand_id`…) **ayrı tutuldu** — "sistem ne dedi" ile "envantere ne yazılacak"
karışmasın. Ayrıca `normalized_name` (geri-join), `rows` (etki), `needs_review`,
`judged`, `parent_decided_by`, `gate_*_verdict` (denetim) ve `result_json`.

---

## 10. Doğrulama

| kontrol | sonuç |
|---|---|
| mevcut test takımı | **221/221 geçti** (değişiklik öncesi ve sonrası) |
| mod, 500 gerçek sorgu | **500 ok, 0 hata** |
| kararlar gate-batch ile aynı mı | **evet** — 217/213/47/23, birebir |
| `needs_review` oranı | **260/500 = %52,0** — öngörülen hakem yüküyle birebir |
| hız | 0,339 sn/sorgu (gate-batch'te 0,39 → %13 daha hızlı) |

### 10.1 (b)'nin A/B'si (150 sorgu, aynı oturum)

| | |
|---|---:|
| kapalı (bugünkü çekirdek) | 411,1 ms/sorgu |
| açık (mod) | 343,6 ms/sorgu |
| kazanç | **%16,4** |
| **tamamen aynı karar (id dahil)** | **150/150** |

Vektör sapması ölçüldü: maks. mutlak fark **3,3e-07**, kosinüs 0,9999998.
Örneklemde hiçbir kararı çevirmedi — yine de çekirdekte kapalı bırakıldı.

### 10.2 Bulunan ve düzeltilen kusur

İlk koşuda subunit aday kaydı 385 olması gerekirken **6** çıktı. Sebep: gate,
`review`/`no_match`in "exact yok" dalında `matched_id=None` döndürüyor
(`gate/gate.py` `_decide_pool`) — aday yalnız sinyallerde kalıyor. Düzeltme:
kimlik yoksa havuzun en yüksek `token_set_ratio`'lu adayına geri düşülüyor
(gate'in kendi gösterim adayıyla aynı seçim).

Düzeltme sonrası: parent 217 karar + 283 aday = 500; subunit 72 karar + 385 aday
+ 43 birim-ifadesiz = 500; **kimliksiz kalan satır 0**; kararlar değişmedi.

---

## 11. Süre tahminleri

286.948 sorgu için:

| senaryo | süre |
|---|---:|
| gate-only (`--no-judge`), mod ile | **~27 saat** |
| yalnız parent + hakem | ~41 gün |
| parent + subunit (bugünkü `decide()`) | ~63 gün |
| **gate-only, ilk 20.000 sorgu** (satırların %65,4'ü) | **~2 saat** |

Bir sorgu ortalama 7,4 satır dolduruyor; süre 4,3M satıra değil, 286.948 sorguya bağlı.

---

## 12. Açık işler

**Yapılmadı / karara bağlı:**

1. **Birleştirme betiği yok.** Sonuç CSV'sini envantere geri yazacak adım
   (`normalized_name` üzerinden join, yeni sütunlar) yazılmadı.
2. **`source=legacy` bayrağı** — `trusted_legacy_answers.csv`'deki 14.591 ad eski
   uzayda; birleştirmede ayırt edilmeli (§5.2).
3. **Genel adlı katalog kayıtları** ölçülmedi (§6.1). Tam koşudan önce yapılmalı:
   `State Hospital` / `University School` gibi kaç kayıt var, batch girdisinin
   ne kadarını çekiyorlar? Kara liste/ceza kuralı `auto_match` kesinliğini
   doğrudan yükseltir.
4. **Hakemli koşu hiç denenmedi.** Mod `--judge` yolundan bir kez bile
   geçmedi; ölçümlerin tamamı `--no-judge`.
5. **(c) sorgular arası batch** ertelendi (§7.1).
6. **Kapsam dışı bırakılan kümeler:** parent'ı dolu ama subunit'i boş 2.908.472
   satır; ve dolu satırlara bizim kararımızı da yazma seçeneği.
7. **`jobs/inventory.py` için birim testi yok.** Mevcut 221 test çekirdeği
   koruyor ama yeni modu kapsamıyor.

**Hiçbir şey commit edilmedi.** Çalışma ağacı: `cli/main.py`,
`embedding/query_encoder.py`, `retrieve/resolve.py` değişik; `jobs/` yeni.

---

## 13. Bilinen riskler

- **Çapraz kontrol seti gold değil.** `trusted_legacy_answers.csv`'deki 14.591 ad
  bir tutarlılık kontrolü sağlar ama (i) id'ler farklı uzayda, yalnız adlar
  karşılaştırılabilir; (ii) eski cevabın kendisi eskimiş olabilir; (iii) set
  kolay tarafa yanlı (büyük Türk üniversiteleri). Düşük uyum alarmdır, yüksek
  uyum kanıt değildir.
- **`auto_match` kesinliği bu sette ölçülmedi.** %98 hedefine göre nerede
  olduğumuz bilinmiyor; §6.1'deki genel-ad çekimi bilinen bir sızıntı.
- **Kalan set eski ölçümlerden zor.** Hakem payı %58 → %78,4. `benchmark_500_sample`
  üzerinde kalibre edilmiş eşikler bu dağılımda aynı davranmayabilir.
