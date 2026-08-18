# Kod Öğrenme Yol Haritası

*Amaç: sistemin tamamına hakim olmak. Sıra, çalışma zamanı akışını takip eder —
her aşama bir öncekinin üzerine oturur, "bu neden var" sorusu kendiliğinden
cevaplanır. Klasör listesi alfabetik değil, bilinçli sıralanmış.*

Nasıl kullanılır: her aşamada önce dosyaları belirtilen sırayla oku, sonra
"Kendine sor" bölümündeki soruları cevaplamaya çalış (bana sorabilirsin, ama
önce kendin denemen kalıcılığı artırır). Aşama sonunda "Doğrulama" kısmında
küçük bir egzersiz var.

---

## 0) Büyük resim — 10 dakika

Önce şu iki dosyayı oku, kod değil ama sistemin "neden"ini anlatıyor:
- `docs/PROJE_RAPORU.md` — sistemin ne yaptığı, üst düzey
- Bu depodaki en son `docs/RAPOR_*.md` / `docs/ANALIZ_*.md` dosyalarından biri (tarihe göre en yeni) — güncel neyle uğraştığımızı gösterir

**Kendine sor:** Sistem hangi girdiyi alıp hangi çıktıyı üretiyor? "Kurum
çözümleme" (institution resolution) ne demek, somut bir örnek düşün.

---

## 1) `normalize/` — girdi temizleme

Dosyalar (bu sırayla): `abbreviations.py` → `qualifiers.py` → `query_pipeline.py`

Bu katman, pipeline'ın en başı — ham kurum adı metni (kirli, kısaltmalı,
çok dilli) buradan geçip standartlaşıyor.

**Kendine sor:** `query_pipeline.py`'daki ana fonksiyon ne alıyor, ne
döndürüyor? Bir kısaltma (örn. "Üni.") nasıl açılıyor?

---

## 2) `elastic/` + `embedding/` — veri katmanı

Dosyalar: `elastic/mappings.py` → `elastic/client.py` → `elastic/document.py` →
`elastic/indexer.py` → `elastic/search.py`, sonra `embedding/encoder.py` →
`embedding/query_encoder.py` → `embedding/text_builder.py`

Katalogdaki kurumlar nasıl saklanıyor (Elasticsearch şeması), nasıl vektöre
çevriliyor (embedding), nasıl aranıyor (bm25 + kNN).

**Kendine sor:** İki ayrı indeks var mı (parent/subunit)? `search.py`'de bm25
ve kNN aramaları nasıl birleşiyor (RRF - Reciprocal Rank Fusion nedir)?

**Doğrulama:** `elastic/search.py` içinde `search_knn` fonksiyonunu bul,
hangi embedding fonksiyonunu çağırdığını takip et.

---

## 3) `retrieve/` — aday bulma (`resolve()`)

Dosyalar: `decompose.py` → `resolve.py`

Bu, bugün en çok konuştuğumuz katman. Bir sorgu geldiğinde: hipotezlere
bölünüyor (`decompose`), her hipotez için aday havuzu (parent + subunit)
çekiliyor (`resolve`).

**Kendine sor:** "Hipotez" ne demek, neden sorgu tek parça olarak değil de
parçalara bölünerek aranıyor? `resolve()`'ın döndürdüğü `ResolveResult` neyi
taşıyor?

**Doğrulama:** `jobs/inventory.py` içinde `_resolve` nasıl çağrılıyor, hangi
parametreler geçiliyor (`encode_prewarm` dahil) - bunun ne işe yaradığını
`embedding/query_encoder.py`'de `prewarm()`'a bakarak anla.

---

## 4) `gate/` — kural-tabanlı karar

Dosyalar: `gate.py` (tek dosya, ama uzun - sabırlı oku)

LLM'siz, deterministik karar katmanı. `auto_match` / `review` / `ambiguous` /
`no_match` etiketlerinin her biri hangi kurala göre veriliyor?

**Kendine sor:** "tam eşleşme" (exact match) neden bu kadar önemli? bm25/kNN
skorları karar için mi kullanılıyor yoksa sadece sıralama için mi?

**Doğrulama:** Bugün bulduğumuz "State Hospital" / "City Hospital" sorununu
hatırla (§6.1, `docs/RAPOR_2026-08-11_envanter_modu.md`) - `gate.py`'de bu
hatanın kök nedenini (jenerik ada aşırı güven) bul.

---

## 5) `judge/` — LLM hakem katmanı (F4)

Dosyalar: `schema.py` → `candidates.py` → `prompt.py` → `client.py` →
`judge.py`

Gate karar veremediğinde devreye giren LLM (Gemma4:e4b, Ollama). Şema neden
bu kadar kısıtlı (`_decision_schema`), prompt nasıl kurulmuş, model çıktısı
nasıl doğrulanıyor (halüsinasyon kontrolü).

**Kendine sor:** `confidence` alanı neden `ParentDecision`/`SubunitDecision`'da
YOK? (dün bulduğumuz bug'ın kök nedeni buydu - `jobs/inventory.py` içinde
`getattr` ile düzeltildi, git log'da `5d16bd3` commit'ine bak.)

**Doğrulama:** `judge/prompt.py`'nin en üstündeki docstring'i oku - hangi
tasarım kararları (reasoning kaldırıldı, kosinüs kaldırıldı vb.) neden
alınmış, tarihleriyle birlikte yazıyor.

---

## 6) `decide/` — gate+judge birleşimi

Dosyalar: `decide.py`

Normal (envanter-dışı) akışta gate ve judge'ı birleştiren üst katman.
`jobs/inventory.py`'nin NEDEN bunu kullanmadığını (subunit hakemi tetiklemiyor
farkını) `jobs/inventory.py`'nin başındaki docstring'le karşılaştırarak anla.

**Kendine sor:** `decide()` ile `jobs/inventory.py`'deki
`process_one_inventory()` arasındaki fark tam olarak ne?

---

## 7) `jobs/` + `eval/` — toplu iş altyapısı

Dosyalar: `eval/csv_runner.py` (temel motor) → `eval/gate_batch.py` →
`eval/decide_batch.py` → `eval/batch.py` → `jobs/inventory.py` (hepsini
kullanan en özelleşmiş mod)

`run_csv_batch`'in resume/worker mantığını anla - bugün defalarca kullandık.

**Kendine sor:** `--resume` nasıl çalışıyor (hangi kolona göre "zaten
yapılmış" kararı veriliyor)? `max_workers` neden `ThreadPoolExecutor`
kullanıyor, `multiprocessing` değil?

**Doğrulama:** Bugün üç ortamda (yerel/Colab/Kaggle) paralel çalıştırdığımız
`inventory-batch` komutunun tam çağrı zincirini `cli/main.py`'den
`jobs/inventory.py`'ye kadar takip et.

---

## 8) `cli/` + `api/` — dış yüzler

Dosyalar: `cli/main.py` (komutlara genel bakış, hepsini okumana gerek yok,
`inventory-batch` ve `judge` komutlarına odaklan) → `api/app.py` →
`api/deps.py` → `api/schemas.py` → `api/jobs.py`

CLI ile API aynı çekirdek fonksiyonları mı çağırıyor? API'nin production'da
nasıl kullanıldığını (senkron mu async mi, job kuyruğu var mı) anla.

**Kendine sor:** API Docker imajı src ile senkron mu? (Hafızada bir not
vardı bu konuda - `dalga0_1_2_oturumu` notuna bak, güncel olup olmadığını
kontrol et.)

---

## 9) `ingest/` — veri hazırlama (opsiyonel, en sona bırakılabilir)

Dosyalar: `raw_loader.py` → `canonicalize.py` → `build.py`

Bu katman çalışma zamanında (runtime) kullanılmıyor - katalog kurulurken
(bir kerelik/periyodik) çalışıyor. Sistemin günlük işleyişini anlamak için
şart değil, ama "katalogdaki veriler nereden geldi" sorusuna cevap veriyor.

---

## 10) Bitirme egzersizi — gerçek bir görev

Yol haritasını bitirince, küçük gerçek bir değişiklik yap (örn. bilinen bir
küçük hata, ya da küçük bir iyileştirme) - ben rehberlik ederim ama kodu sen
yaz. Bu, pasif okumadan çok daha kalıcı.

Aday görevler (bu oturumda konuşulan, henüz çözülmemiş):
- `gate.py`'de "genel adlı katalog kayıtları çekim merkezi" sorununa
  (State Hospital/City Hospital) bir kara liste/ceza kuralı ekleme
  (bkz. `docs/RAPOR_2026-08-11_envanter_modu.md` §6.1)
- `jobs/inventory.py` için birim testi yazma (rapor §12'de "yok" diye not
  edilmiş)
