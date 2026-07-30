# eval/ — analiz (2026-07-29)

Kapsam: `eval/csv_runner.py`, `eval/batch.py`, `eval/gate_batch.py`,
`eval/decide_batch.py` + CLI'daki üç batch komutu.

Kanıt: **[Ö]** ölçüldü/çalıştırıldı · **[K]** kod okumasıyla kesin.

---

## 1. Rol ve genel değerlendirme

Üç batch türü: LLM-only (`batch`), gate-only (`gate-batch`), hibrit
(`decide-batch`). Ortak CSV yazım/resume/limit mekaniği `csv_runner.py`'de
tek yerde.

**Doğru olanlar:**
- **Satır-bazlı hata izolasyonu**: bir sorgu patlarsa batch çökmüyor,
  `status=error` yazılıp devam ediliyor. 438k satırlık bir işte bu şart.
- **Progressive yazım + flush**: çökme durumunda iş kaybolmuyor.
- **`result_json`** kolonu tam sadakat taşıyor — düz kolonlar okunabilirlik
  için, JSON denetim için.
- `decide_batch`'in **gate sinyallerini her satırda** (LLM'e düşen satırlarda
  dahi) yazması: "hangi satır neden LLM'e düştü" sonradan denetlenebiliyor.
  İyi bir gözlemlenebilirlik kararı.
- `resolve_fn`/`judge_fn`/`gate_fn` enjekte edilebilir → testler ES/Ollama'sız.
- Üç batch'in ortak döngüsünün `csv_runner`'a çıkarılmış olması.

---

## 2. Eksikler

### B1 — `--limit N --resume` birlikte kullanıldığında İŞ İLERLEMİYOR **[Ö]**

`csv_runner.run_csv_batch`:

```python
for count, query in enumerate(queries, start=1):
    if limit is not None and count > limit: break
    if query in done: n_skip += 1; continue
```

`limit` **girdi satırlarını** sayıyor, atlananlar dahil. Yani ikinci koşuda ilk
N satır zaten yapılmışsa, limit onları saymayı bitirip döngüyü kırıyor.

Canlı çalıştırıldı (10 sorgu, `limit=3`):

```
1) ilk koşu,   limit=3            -> ok=3  skipped=0   ✓
2) resume=True limit=3            -> ok=0  skipped=3   ✗ hiç ilerlemedi
3) resume=True limit yok          -> ok=7  skipped=3   ✓
```

`--limit 1000 --resume` komutunu tekrar tekrar çalıştırarak büyük bir batch'i
parça parça ilerletmek — bu iki bayrağın birlikte var olmasının **tek makul
gerekçesi** — çalışmıyor. Üç CLI komutunun da (`gate-batch`, `batch`,
`decide-batch`) ikisini birden sunuyor olması bunu erişilebilir bir tuzak yapıyor.

**Düzeltme:** `limit`, **işlenen** satırı saysın (atlananları değil) — 2 satır.

### B2 — Tekrarlı sorgular `resume` ile SESSİZCE düşüyor **[Ö]**

`done` bir `set` ve dedupe anahtarı sorgu metninin kendisi. Canlı:

```
girdi ["a","b","a"], resume YOK  -> 3 satır yazıldı   ✓
girdi ["a","b","a"], resume VAR  -> 2 satır yazıldı   ✗ ikinci "a" yutuldu
```

Yani `--resume` bayrağı **çıktının satır sayısını değiştiriyor**. Gerçek girdi
v2'nin `raw_name` kolonu (438k satır serbest metin) — tekrar beklenen bir şey.
Girdi ile çıktı satırlarını 1:1 hizalamaya çalışan biri sessizce yanlış hizalar.

**Düzeltme:** resume anahtarı `(satır_no, query)` olsun ya da çıktıya bir
`row_index` kolonu eklensin.

### B3 — `resume` mevcut başlığı DOĞRULAMIYOR **[K]**

Dosya varsa `mode="a"` ile açılıp `writer.writeheader()` atlanıyor. Ama mevcut
dosyanın başlığının şu anki `FIELDNAMES` ile aynı olduğu **kontrol edilmiyor**.
`gate_batch.FIELDNAMES` bu projede zaten büyüdü (P2 sonrası sinyal kolonları);
eski bir çıktıya `--resume` ile eklemek, kolonları kaymış bir CSV üretir ve
hiçbir hata vermez. Tek `if` ile kapanır.

### B4 — Eşik kalibrasyonu, kalibrasyon aracıyla YAPILAMIYOR **[K]**

`process_one_gate` gate'i `gate_fn(res)` diye çağırıyor — `config` parametresi
yok. `run_gate_batch` de config almıyor. CLI'da da bayrak yok.

Yani `gate.garbage_lexical_floor`'u süpürüp (0.40 / 0.50 / 0.55 / 0.65) hangi
eşiğin ne dağılım verdiğini ölçmek — **sıradaki iş listesinin 1. maddesi**
("eşiklerin gold ile kalibrasyonu") — bu araçla mümkün değil. Programatik olarak
`gate_fn=lambda r: gate(r, config=...)` ile aşılabilir ama ne CLI ne API bunu
sunuyor.

**Düzeltme:** `run_gate_batch(..., config=None)` → `gate_fn(res, config=config)`
+ CLI'ya `--gate-floor`. Küçük iş, doğrudan bir sonraki adımı açıyor.

### B5 — Gold kolonu / skorlama HİÇ YOK **[K]**

Üç batch de yalnız tahmin yazıyor. Hiçbirinde `--gold-col`, doğru/yanlış
karşılaştırması, precision/recall özeti yok. `config/default.yaml`
`decision.auto_precision_target: 0.98` diye bir hedef tanımlıyor ama bu hedefi
**ölçebilecek bir kod yok** (ve o config anahtarı da okunmuyor — bkz.
`07_api_cli_config.md`).

Bu, tüm analiz serisindeki en büyük tek eksik: dört rapordaki iyileştirme
önerilerinin hiçbiri, etkisi ölçülmeden güvenle uygulanamaz.

**Durum güncellemesi (2026-07-29):** *veri* tarafı kısmen çözüldü —
`data/eval/benchmark_500_sample.csv` (500 sorgu, çok eksenli kategorili, 39
doğrulanmış `beklenen=no_match`). Ama **skorlayacak kod hâlâ yok**, ve 39 satır
dışında gold etiket yok (v2'deki `real_labeled.csv` geçersiz çıkıp silindi).
Yani B5 tamamen açık; girdi hazır, ölçüm makinesi yok.

### B6 — CLI'da üç komut ~50 satır kopya-yapıştır **[K]**

`gate_batch_cmd` / `decide_batch_cmd` / `batch_cmd`: girdi dosyası kontrolü,
başlık doğrulaması, `_queries()` üreteci, `_progress()` yazıcısı ve bitiş özeti
üçünde de neredeyse birebir aynı. Yazma tarafı `csv_runner`'a çıkarılmış, okuma +
CLI tarafı çıkarılmamış. B1/B2/B3 düzeltmesi yapılırken bu üçlemenin de tek yere
inmesi mantıklı (yoksa aynı düzeltme üç yere elle uygulanacak).

### B7 — `csv_runner.py` için HİÇ test yok **[Ö]**

Testlerde import edilmiyor. B1, B2 ve B3'ün tamamı bu dosyada ve üçü de test
edilmemiş yollarda. Üç batch türünün ortak omurgası, kapsam dışı tek modül.

### B8 — `decide_batch_cmd` `OllamaClient`'ı kapatmıyor **[K]**

CLI'da `OllamaClient(...)` kuruluyor ama `close()` / context manager yok.
Süreç sonunda işletim sistemi topluyor — pratikte zararsız, ama sınıf `__enter__`/
`__exit__` sağladığı halde kullanılmaması bir tutarsızlık.

---

## 3. Öneriler (öncelik sırasıyla)

| # | İş | Neden | Maliyet |
|---|---|---|---|
| 1 | **B7** `csv_runner` testleri (önce kırmızı) | B1/B2/B3 burada yaşıyor | küçük |
| 2 | **B1** `limit` işlenen satırı saysın | belgelenmiş kullanım hiç çalışmıyor | 2 satır |
| 3 | **B2** resume anahtarına satır no | `--resume` çıktı satır sayısını değiştiriyor | küçük |
| 4 | **B3** başlık doğrulaması | sessiz kolon kayması | 3 satır |
| 5 | **B4** `--gate-floor` / config geçişi | eşik kalibrasyonunu mümkün kılar | küçük |
| 6 | **B5** `--gold-col` + özet metrikleri | tüm iyileştirmelerin ön koşulu | orta |
| 7 | **B6** üç CLI komutunu tek yere indir | düzeltmeler tek yerde uygulansın | orta |

**Sıralama önemli:** B5 olmadan diğer raporlardaki hiçbir öneri "işe yaradı mı"
sorusuna cevap veremez. B4+B5 birlikte, gate eşiklerinin gold ile kalibre
edilmesi işini (sıradaki iş listesi #1) fiilen mümkün kılan minimum pakettir.

## 4. Değiştirilmemesi gerekenler

- Satır-bazlı hata izolasyonu + progressive flush.
- `result_json` tam-sadakat kolonu.
- `decide_batch`'in gate sinyallerini her satıra yazması.
- Fonksiyon enjeksiyonu (test edilebilirlik).
