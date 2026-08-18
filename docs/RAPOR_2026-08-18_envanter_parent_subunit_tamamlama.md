# RAPOR — Envanter çalışması: teşhis, doldurma, temizlik, yeniden yapılandırma (2026-08-18)

Tek oturumun tam kronolojik kaydı. Kapsam: `institution-field-inventory.csv`
(8.920.512 satır) içindeki `parent_name`/`subunit_name` boşluklarının LLM'e
sormadan mümkün olduğunca kapatılması, sonucun tek bir özet CSV'de
toplanması, oturum sırasında bulunan repo dağınıklığının temizlenmesi,
dosya yapısının yeniden düzenlenmesi, ve API/Docker eksikliklerinin
giderilmesi. Commit YOK.

---

## Bölüm A — Teşhis: neden 2,2 milyon satır boş kalmıştı

### A.1 Tetikleyici soru
`institution-field-inventory-resolved.csv`'de hem `resolved_parent_match`
hem `resolved_parent_name` hem `parent_name` boş olan satır var mı? **Evet
— 2.206.663 satır.**

### A.2 Neden böyle kalmış
`scripts/merge_inventory_resolved.py`'nin mantığı incelendi: `parent_name`
boş olan satırlar `main_batch/temiz_sonuc.csv`'de (LLM/gate batch sonucu,
287.841 satır) aranıyor; bulunursa `resolved_*` dolduruluyor, bulunamazsa
bilerek boş bırakılıyor ("işlenmedi" ile "no_match" karışmasın diye).

Ölçüm: kaynak envanterde `parent_name` boş olan satırların **301.521
benzersiz `normalized_name`'i** var, ama `temiz_sonuc.csv` bunların sadece
**286.929'unu** kapsıyor → **14.592 ad batch kuyruğuna hiç girmemiş.**
"pamukkale universitesi" gibi sıradan bir ad bile bu kayıp kümedeydi —
rastgele değil, sistematik bir kapsam boşluğu.

### A.3 Duplike-isim analizi ve `current_institution_id` denemesi
Kullanıcı sordu: bu 14.592 addan bazıları duplike olup içlerinde
`parent_name` dolu olan var mı? **Evet, 14.591'i** aynı `normalized_name`'in
kaynakta başka satırlarda zaten dolu göründüğü "karışık" gruplardandı.

Kullanıcının önerisi test edildi: `current_institution_id` bazında gruplama
— **0 sonuç** verdi, çünkü her `current_institution_id` ya tamamen dolu ya
tamamen boş (hiç karışık grup yok). Doğru anahtarın `normalized_name`
olduğu doğrulandı (14.607 karışık grup). Ayrıca `resolved_parent_id`
sütununda da benzer bir tutarsızlık olup olmadığı kontrol edildi — hiç
tutarsızlık bulunmadı, sorun sadece kaynak `parent_name`'deydi.

---

## Bölüm B — Doldurma çalışması

### B.1 İlk deneme — TERK EDİLDİ
`scripts/backfill_resolved_from_source_parent.py`: `resolved_parent_name`'i
`source_backfill` etiketiyle doldurma denemesi. Kullanıcı "etiketle ayırt
etmeyelim" dedi ve yaklaşım tamamen değişti: **ham `parent_name`/
`subunit_name` sütununun kendisini** doldurmaya karar verildi. Script repo'da
referans amaçlı duruyor, hiçbir zincirde kullanılmıyor.

### B.2 Asıl çözüm — `scripts/backfill_parent_subunit_by_name.py`
`normalized_name` grubu içinde `parent_name` doluysa (`parent_id`/
`parent_name`/`parent_iz` tutarlıysa) boş satırlara kopyalanır; `subunit_name`
de tutarlıysa o da kopyalanır. `subunit_id`/`subunit_iz` **hiçbir zaman**
kopyalanmaz — Gazi Üniversitesi örneğiyle bunların satıra özel (kaynak
sistemin o satıra verdiği kendi kayıt numarası) olduğu doğrulandı.

- **2.206.663 satır dolduruldu** (2.097.220 parent+subunit, 109.443 sadece
  parent — 104 grupta subunit yazımı tutarsızdı, örn. büyük/küçük harf)
- 19 grup gerçekten çelişkili (aynı ad, farklı gerçek kurum — örn.
  "institute of science" iki ayrı üniversiteye bağlı) → hiç dokunulmadı

**Sonuç: `parent_name` boşluğu %48,5 → %0.**

### B.3 Kataloğa isim eşleme — `scripts/backfill_resolved_id_from_catalog_name.py`
Soru: resolver'a hiç girmeyen, parent'i ham `parent_name`'de olan satırlar
bizim `parent_canonical.jsonl` listemizle eşleşir mi? 6.802.702 satırdaki
**338 benzersiz ad** kontrol edildi:

- 236 ad (6.481.495 satır) katalogda **birebir tek** kayda eşleşti
- 15 ad katalogda **iki farklı id'ye** denk geldi (bkz. B.5)
- 87 ad hiç eşleşmedi (bkz. B.4)

### B.4 Elle eşleştirme — MEB, askeri, rename
Eşleşmeyen 87 ad kategorize edildi ve kullanıcı onayıyla elle bağlandı:

| grup | ad sayısı | satır | katalog id |
|---|---:|---:|---|
| MEB (şehir/kampüs eki atıldı) | 23 | 16.509 | 10740 |
| Askeri (2016'da Milli Savunma Üniversitesi çatısında birleşti) | 8 | 1.918 | 273 |
| Rename (kurum aktif, isim değişmiş — Adnan Menderes→Aydın Adnan Menderes vb.) | 25 | 156.404 | (her biri kendi id'sine) |

Rename listesi önce katalog içinde subsequence/alias aramasıyla doğrulandı
(23/25 katalogda iz bırakıyordu), 2'si ("İstanbul Bilim Üniversitesi",
"Anadolu Üniversitesi Eskişehir İktisadi ve Ticari İlimler Akademisi")
katalogda iz bırakmıyordu — kullanıcı bunların doğruluğunu onayladı.

### B.5 Mükerrer katalog kaydı — `scripts/backfill_duplicate_catalog_manual.py`
15 addaki çift-id sorunu incelendi: her çiftte bir kayıt `canonical_ref:
"ror:..."` (uluslararası ROR kaydı), diğeri `"yok:..."` (YÖK kaydı) — aynı
kurum, iki kaynak sistemden gelip hiç birleştirilmemiş. Kullanıcıya soruldu,
**YÖK referanslı id** seçildi (ham veri Türkiye kaynaklı olduğu için) →
**137.090 satır.**

**Sonuç: katalog eşleşme oranı %97,3 → %99,86.**

### B.6 Nihai özet tablosu — `scripts/build_final_summary_csv.py`
Kullanıcının istediği şema tartışıldı ve netleştirildi: satır-bazlı (8,9M,
benzersizleştirme yok), `current_institution_name`+`normalized_name`,
birleşik `parent_name`/`parent_id`, `kaynak` (ror/yok), ayrı `parent_match`/
`subunit_match` sütunları, `subunit_name`/`subunit_id` **sadece resolver'dan**
(ham veri kullanılmaz, kataloğumuzla hizası garanti değil).

`subunit_match` kuralı için bir keyword-heuristic tasarlandı ve iki kez
daraltıldı (ilk liste top-level kurum adlarında da geçen kelimeler
—"hastane", "başkanlık", "akademi", "okulu"— yüzünden yanlış pozitif
üretiyordu; 500K+ satırlık örneklemle doğrulanıp 10 kelimeye indirildi):
girdi metninde fakülte/bölüm/enstitü/yüksekokul/program/anabilim dalı/bilim
dalı/uygulama ve araştırma ifadesi varsa `review`, yoksa `yok`.

---

## Bölüm C — Nihai istatistikler

**Parent:**

| `parent_match` | satır | oran |
|---|---:|---:|
| `match` | 8.185.464 | %91,8 |
| `no_match` | 327.864 | %3,7 |
| `review` | 307.647 | %3,4 |
| `judge_error` | 99.537 | %1,1 |

**Subunit:**

| `subunit_match` | satır | oran |
|---|---:|---:|
| `yok` | 5.410.872 | %60,7 |
| `review` | 2.293.739 | %25,7 |
| `no_match` | 727.417 | %8,2 |
| `match` | 388.947 | %4,4 |
| `judge_error` | 99.537 | %1,1 |

Not: `subunit_match='review'` olan 2.293.739 satırın **1.802.672'sinde ham
`subunit_name` aslında dolu** — bilgi var ama backfill kuralı gereği (B.6)
kullanılmadı. Gerçek "hiç bilgi yok" satır sayısı 491.067.

---

## Bölüm D — Temizlik

### D.1 docs/ klasörü
Kullanıcı önceden sildiği `docs/` klasörünü (güncelliğinden emin olmadığı
için) geri koymuştu. İçerik gözden geçirildi: `DENEY_*`/`RAPOR_*` dosyaları
bilinçli tarihsel kayıt (kendi docstring'leri bunu söylüyor) — dokunulmadı.
`docs/DURUM.md` ve `docs/DURUM_2026-07-27.md` ("güncel durum" için yazılmış
ama 3 haftadır güncellenmemiş, artık `MEMORY.md`'nin işlevini tekrarlıyor)
**silindi.**

### D.2 `main_batch/` — bağımlılık zinciri çıkarılıp gereksiz ara dosyalar silindi
`inventory_v4ec-colab.csv`, `kaggle_v4ec_forward.csv`, `birlesik_v4ec.csv`
(düzeltilmemiş hali) silindi (~254MB) — `birlesik_v4ec_duzeltilmis.csv`
(elle düzeltilmiş, tekrar üretilemez) + `gate_batch_inventory.csv` +
`duzeltmeler/` + `temiz_sonuc.csv` kaldı.

**Bilinen yan etki:** Bu silme, `scripts/ab_coverage_weight.py`,
`scripts/olc_decompose.py`, `scripts/olc_yanlis_pozitif.py`'yi kırdı (üçü de
düzeltilmemiş `birlesik_v4ec.csv`'yi okuyor). Hiçbir dokümantasyon bu
script'lere referans vermiyor, sonuçları muhtemelen zaten kaydedilmiş
(`decompose akronim defekti` hafıza notu, 2026-08-17) — kullanıcı kararıyla
**şimdilik düzeltilmedi**, bozuk bırakıldı.

### D.3 `faz0_sonuc/` klasörü (12,4MB) silindi
`docs/RAPOR_2026-08-14_llm_katmani_deneyleri.md`'nin kendi notuyla teyit
edildi: *"Deney kodu ve ham çıktı CSV'leri kullanıcı kararıyla oturum
sonunda SİLİNDİ"* — bu klasör, `docs/` geri konurken yanlışlıkla geri gelmiş
kalıntıydı. Aynı gerekçeyle 3 ilgili notebook da silindi: `colab_judge_ab_faz0.ipynb`,
`kaggle_judge_ab_faz0.ipynb`, `kaggle_faz0_v5.ipynb`.

### D.4 Diğer küçük temizlik
- `.DS_Store`, `.Rhistory` (kesin çöp, zaten gitignored)
- `output/` klasöründe 19 dosya silindi, sadece `decide_baseline_dalga1_2026-08-06.csv`
  kaldı (`RAPOR_2026-08-07_optimizasyon.md`'de referans var)
- `kaggle_judge_sonuc.csv` silindi (hiçbir yerde referans yok)
- `scripts/merge_judge_outputs.py` silindi (`merge_runs.py`'nin kendi
  docstring'i onu "yerine geçtiği" script olarak işaretliyor)
- `TURKIYE_BAKANLIK_DEVLET_KURUMLARI.md`, `YABANCI_BAKANLIK_DEVLET_KURUMLARI.md`,
  `YOK_KAYNAKLI_PARENT_KAYITLARI.md` + 2 `temiz_sonuc_*.csv` → **silinmedi**,
  `docs/`'a taşındı (tamamlanmış, belgelenmiş bir yan-iş)
- 3 dağınık `.DS_Store` (docs/, data/, data/jobs/) son bir taramada bulunup
  silindi

### D.5 Dokunulmayan, değerli bulunan dosya
**`pasif_parent_kayitlari.csv`** (bu oturumdan önce, başka bir oturumda
üretilmiş) çöp sanılıp incelendi, tam tersine değerli çıktı: `data/raw/
institution_parent.csv`'nin (`active=false`) elle çıkarılmış bir alt kümesi
— Bölüm B'de bulunan rename/kapatılmış-üniversite/askeri-kurum grubunun
neredeyse tamamını zaten `canonical_ref` ile içeriyor. Silinmedi, ayrı bir id
uzayında olduğu not edildi (bkz. Bölüm F).

---

## Bölüm E — Dosya yapısı yeniden düzenleme

### E.1 Taşıma
Kök dizinde gevşek duran 7 `institution-field-inventory-*.csv` +
`pasif_parent_kayitlari.csv` yeni **`data/inventory/`** klasörüne taşındı
(projenin `data/raw|processed|jobs|eval` konvansiyonuna uydu). 8 script'te
path referansları güncellendi.

### E.2 Yeniden adlandırma
Tartışılan sorunlar: uzun/tekrarlı `institution-field-inventory-` öneki
(klasör bağlamı zaten yeterli), `resolved-final3.csv` kötü bir isim (sanki
hâlâ bir versiyon zinciri varmış izlenimi), `summary-yok.csv` kelime
çakışması riski ("yok" = YÖK kısaltması ama Türkçe'de "mevcut değil" de
demek), `pasif_parent_kayitlari.csv`'nin snake_case tutarsızlığı.

| eski | yeni |
|---|---|
| `institution-field-inventory.csv` | `raw.csv` |
| `institution-field-inventory-normalized.csv` | `normalized.csv` |
| `institution-field-inventory-normalized-backfilled.csv` | `normalized-backfilled.csv` |
| `institution-field-inventory-resolved.csv` (SADECE LLM) | `resolved-llm-only.csv` |
| `institution-field-inventory-resolved-final3.csv` (LLM+manuel) | `resolved-merged.csv` |
| `institution-field-inventory-summary.csv` | `summary.csv` |
| `institution-field-inventory-summary-yok.csv` | `summary-yok-kaynakli.csv` |
| `pasif_parent_kayitlari.csv` | `pasif-parent-kayitlari.csv` |

8 script yeniden güncellendi; `py_compile` + dosya varlığı + gerçek
header/ilk-satır okuma testiyle doğrulandı — sistem bozulmadı.

### E.3 Silinen ara-zincir dosyaları (~7,05GB)
`resolved-backfilled.csv` (terk edilmiş deneme, B.1), `resolved-catalog-
backfilled.csv`, `resolved-final.csv`, `resolved-final2.csv` (B.3-B.4'ün ara
adımları, `resolved-merged.csv` tarafından tamamen kapsanıyor),
`institution-field-inventory-todo.csv` (eski batch kuyruğu, artık hiçbir
script kullanmıyor).

---

## Bölüm F — API/Docker eylem planı

Temizlik sırasında bulunan bir yan-keşif: envanter modu (`jobs/inventory.py`)
sadece CLI'dan çalıştırılabiliyordu, API'de yoktu; Docker'da `data/inventory`
hiç mount edilmemişti. Beş adımlı bir plan üzerinde anlaşıldı ve uygulandı:

1. **`POST /batch/inventory` endpoint'i** (`api/routers/batch.py`) — diğer
   `gate`/`judge`/`decide` batch endpoint'leriyle simetrik. `api/jobs.py` ve
   `api/schemas.py`'deki `JobKind`/`Literal` tiplerine `"inventory"` eklendi.
2. **Docker volume**: `docker-compose.yml`'e `data/inventory` bağlandı.
3. **ES güvenliği** (`xpack.security.enabled=false`) — bu ortamda ES
   çalışmadığı için TLS/auth değişikliği test edilemezdi, kullanıcı kararıyla
   sadece dokümante edildi (`docs/BILINEN_ACIK_ES_GUVENLIK.md`).
4. **`/health`'e embedding model kontrolü** eklendi (`embedding/encoder.py`'ye
   yan etkisiz `is_loaded()`, `HealthResponse.embedding_model` alanı). Job
   durumunun bellek-içi olması zaten `api/jobs.py`'de dokümante edilmişti.
5. **Auth/rate-limit/CORS** — API şu an iç kullanım için (aynı Docker ağı),
   dışa açılmadan önce eklenmesi gerektiği dokümante edildi
   (`docs/BILINEN_ACIK_API_AUTH.md`). Ayrıca 5 yeni test eklendi (`/batch/
   inventory` ve `/batch/judge` uçtan-uca, boş CSV, ardışık job çalıştırma,
   `test_api_batch.py`) — toplam **295/295 test geçiyor.**

---

## Bölüm G — Bilinen açık noktalar / doğal sonraki adımlar

- **9.286 satır (%0,14) hâlâ eşleşmedi**: 23 kapatılmış vakıf üniversitesi
  (6.320 satır), 7 bağımsız meslek yüksekokulu (2.226 satır), 1 belirsiz
  kayıt (740 satır). **`data/inventory/pasif-parent-kayitlari.csv`** (D.5) bu
  grubun neredeyse tamamını zaten içeriyor — doğal sonraki adım.
- **19 gerçek çelişkili ad** (aynı `normalized_name`, farklı gerçek kurumlar)
  bilerek dokunulmadan bırakıldı.
- **Subunit `review`'in %79'u aslında ham veride bilgi taşıyor** (1.802.672
  satır) — ayrı bir backfill turuyla (`subunit_id`/`subunit_iz` olmadan,
  sadece `subunit_name`) doldurulabilir.
- **`main_batch/ab_coverage_weight.py`, `olc_decompose.py`,
  `olc_yanlis_pozitif.py` kırık** (D.2) — tekrar gerekirse Colab/Kaggle
  judge koşusu tekrarlanmalı.
- **ES kimlik doğrulaması ve API auth/rate-limit** eklenmedi, sadece
  dokümante edildi (`docs/BILINEN_ACIK_*.md`) — prod'a geçmeden önce ele
  alınmalı.
