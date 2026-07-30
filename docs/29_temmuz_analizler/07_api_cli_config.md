# api/ + cli/ + config — analiz (2026-07-29)

Kapsam: `api/app.py`, `deps.py`, `jobs.py`, `routers/single.py`,
`routers/batch.py`, `schemas.py`, `cli/main.py`, `config.py`,
`config/default.yaml`, `config/docker.yaml`, `docker/docker-compose.yml`.

Kanıt: **[Ö]** ölçüldü · **[K]** kod okumasıyla kesin.

---

## 1. Rol ve genel değerlendirme

CLI (11 komut) ve API (10 rota) aynı çekirdeği saran iki arayüz. `api/app.py`
docstring'i ilkeyi açıkça koyuyor: *"retrieve/gate/judge/decide/eval
katmanlarına DOKUNULMADI - bu paket sadece onları sarmalar"* — ve gerçekten
uyulmuş.

**Doğru olanlar:**
- **Dependency enjeksiyonu** (`deps.get_*_fn`) → testlerde
  `app.dependency_overrides` ile ES/Ollama'sız test. `eval/batch.py`'deki
  `resolve_fn`/`judge_fn` enjeksiyonuyla aynı ilke, tutarlı.
- **Lifespan ısıtma**: embedding modeli bir kez yükleniyor, tek kalıcı
  `OllamaClient` (CLI'nin aksine her istekte yeni bağlantı kurulmuyor —
  ölçülmüş ~5-8 s gizli maliyet).
- **Batch senkron HTTP'de işlenmiyor** — dosya kaydedilip `JobManager`'a
  atılıyor, `job_id` dönüyor. 438k satırlık girdiler için doğru karar.
- **`max_workers=1`** — batch'ler birbiriyle ve tekli trafikle aynı ES/Ollama'yı
  paylaşıyor; seri çalıştırma kaynak yarışını önlüyor. Gerekçe yazılı.
- **Yükleme yolları sunucu üretimi** (`JOBS_DIR / f"{job_id}_in.csv"`) —
  kullanıcı girdisi dosya yoluna hiç girmiyor, path traversal yok.
- `/health` asla 500 fırlatmıyor (her iki kontrol de `try`'lı).
- Hata yolları: `JudgeValidationError`/`LlmError` → API 502, CLI exit 1. Yutulmuyor.
- `config.py` `lru_cache`'li + `INRES3_CONFIG` env override → Docker'da tek fark
  host adları.

---

## 2. Eksikler

### C1 — Config'in YARISI ölü; dosya kendi kuralını çiğniyor **[Ö]**

`config/default.yaml`'ın ilk satırları:

> Not: bir anahtar burada var diye davranış değişmez; kodda okunduğu yer aranır
> (v2 O6 dersi: **okunmayan ölü anahtar bırakma**).

`src/` üzerinde grep sonucu:

| Anahtar | `src/` hit | Durum |
|---|---|---|
| `retrieval.pool_size` | 0 | **ölü** |
| `retrieval.parent_top_k` | 0 | **ölü** |
| `retrieval.subunit_top_k` | 0 | **ölü** |
| `retrieval.rrf.rank_constant` | 0 | **ölü** (kod `k=60` sabit) |
| `retrieval.boosts.*` | 0 | **ölü + yanlış** (aşağı bkz.) |
| `judge.enabled` | 0 | **ölü** |
| `judge.cache_dir` | 0 | **ölü** (LLM cache'i yok) |
| `judge.auto_confidence` | 0 | **ölü** |
| `decision.auto_precision_target` | 0 | **ölü** |
| `gate.garbage_lexical_floor` | 3 | canlı |
| `embedding.*_prefix`, `batch_size` | 1–3 | canlı |

**En zararlısı `boosts`:**

```yaml
boosts:
  unit_name: 3.0            # BÖYLE BİR ALAN YOK (gerçek ad: name)
  unit_name.ascii: 2.0      # YOK
  aliases.normalized: 1.5   # YOK (gerçek ad: subunit'te aliases_text,
                            #      parent'ta alias_variants.value - 2026-07-30)
  parent_name: 1.0          # var ama kodda 1.5 yazılı
```

Blok **v2 şemasından kalma**. `search.py` boost'ları sabit yazıyor ve değerler
farklı. Bu dosyada boost ayarlayan biri hiçbir etki göremez ve nedenini anlamaz —
config'in kendi uyardığı hatanın tam örneği.

Aynı şekilde `pool_size: 50` yorumu "recall@50 F2'de ölçülür" diyor, ama gerçek
havuz `resolve(size=10)` / CLI `--top 5`. Ölçülen ile çalışan aynı değil.

### C2 — `embedding.dim` iki yerde ayrı sabit **[K]**

`config/default.yaml` `embedding.dim: 768` (okunmuyor) ve
`elastic/mappings.py` `EMBEDDING_DIM = 768` (kullanılan). Model değişirse
ikisinin ayrışması sessiz bir mapping hatası üretir.

### C3 — Job kayıtları ve dosyalar hiç temizlenmiyor **[K]**

- `JobManager._jobs` dict'i **hiç boşaltılmıyor** → uzun ömürlü API sürecinde
  sınırsız büyür.
- `data/jobs/` altındaki `{job_id}_in.csv` ve `{job_id}_out.csv` **hiç
  silinmiyor** → 438k satırlık yüklemeler diskte birikir.

TTL (ör. 24 saat) ya da en azından `DELETE /jobs/{id}` gerekli.

### C4 — Yükleme tamamen belleğe okunuyor, boyut sınırı yok **[K]**

```python
with in_path.open("wb") as f:
    f.write(file.file.read())      # tamamı RAM'e
```

438k satırlık bir CSV onlarca MB. Boyut limiti yok, chunk'lı kopyalama yok
(`shutil.copyfileobj` yeterdi). Kötü niyet gerekmiyor — normal kullanım
senaryosunun kendisi büyük dosya.

### C5 — API batch'te `resume` YOK **[K]**

`jobs.py` docstring'i diyor ki: *"API yeniden başlarsa devam eden job'un durumu
kaybolur … Çıktı CSV'si zaten diskte ve `resume=True` ile elle yeniden
tetiklenebilir."*

Ama `/batch/gate|judge|decide` endpoint'leri yalnız `query_col`, `top`, `limit`
alıyor — **`resume` parametresi yok**. Yani docstring'in önerdiği kurtarma yolu
API üzerinden mevcut değil; yalnızca CLI'dan, elle, aynı dosya yollarıyla
yapılabilir. Belgelenen kurtarma ile gerçek arayüz uyuşmuyor.

### C6 — İptal (cancel) yok, `shutdown(wait=False)` **[K]**

Başlamış bir batch job'ı durdurmanın yolu yok. `lifespan` çıkışında
`shutdown(wait=False)` çağrılıyor; `ThreadPoolExecutor` iş parçacıkları
non-daemon olduğu için yorumlayıcı çıkışta yine de beklenir — yani "beklemeden
kapat" niyeti tam karşılanmıyor. Uzun bir job varken API kapatmak
öngörülemeyen bir süre asılı kalır.

### C7 — `/health` her çağrıda canlı Ollama isteği atıyor **[K]**

```python
r = httpx.get(f"{cfg['judge']['host']}/api/tags", timeout=3.0)
```

Load balancer / container healthcheck saniyede bir vuruyorsa bu, LLM'e sürekli
trafik demek — üstelik `httpx.get` (tek-atış) kullanılıyor, yani `client.py`'de
özellikle çözülen "her çağrıda yeni bağlantı" maliyetinin aynısı burada geri
gelmiş. Kısa TTL'li cache ya da kalıcı client gerekir.

### C8 — Test boşlukları **[Ö]**

`cli/main.py` (426 satır) ve `api/app.py` testlerde **hiç import edilmiyor**.
`config.py` da öyle. Router'lar test edilmiş (`test_api_single/batch`), ama
CLI — kullanıcının fiilen kullandığı arayüz — kapsam dışı. B1/B2 (bkz.
`06_eval_ve_batch.md`) tam olarak CLI bayraklarının birleşiminde yaşıyor.

### C9 — CLI üç batch komutunda kopya-yapıştır **[K]**

Ayrıntı `06_eval_ve_batch.md` B6. Burada tekrar not: düzeltmeler üç yere elle
uygulanmak zorunda kalacak.

---

## 3. Öneriler (öncelik sırasıyla)

| # | İş | Neden | Maliyet |
|---|---|---|---|
| 1 | **C1** ölü config anahtarlarını ya bağla ya sil | dosya kendi kuralını çiğniyor; `boosts` aktif yanıltıcı | küçük |
| 2 | **C4** chunk'lı yükleme + boyut limiti | normal kullanımda RAM baskısı | küçük |
| 3 | **C3** job TTL + `DELETE /jobs/{id}` | bellek + disk sızıntısı | küçük |
| 4 | **C5** API batch'e `resume` parametresi | belgelenen kurtarma yolu yok | küçük |
| 5 | **C7** `/health` Ollama kontrolünü cache'le | LLM'e gereksiz trafik | küçük |
| 6 | **C8** CLI duman testleri (typer `CliRunner`) | en çok kullanılan arayüz testsiz | orta |
| 7 | **C6** job iptali | operasyonel | orta |
| 8 | **C2** `EMBEDDING_DIM`'i config'ten oku | sessiz drift riski | küçük |

**C1 için somut öneri:** `boosts`, `pool_size`, `parent_top_k`, `subunit_top_k`,
`rank_constant` gerçekten bağlanmalı (`search.py` ve `resolve.py` bunları
okusun) — bunlar ayarlanmak *istenen* şeyler ve şu an ayarlanamıyor.
`judge.auto_confidence` ve `decision.auto_precision_target` ise **hedef**,
ayar değil; `docs/`'a taşınıp config'ten silinmeli. `judge.enabled` ve
`judge.cache_dir` için bkz. `05_judge_ve_decide.md` J7.

## 4. Değiştirilmemesi gerekenler

- CLI/API'nin çekirdek katmanlara dokunmayan sarmalayıcı rolü.
- Dependency enjeksiyonu ve `dependency_overrides` ile test yaklaşımı.
- Lifespan ısıtma + tek kalıcı `OllamaClient`.
- Batch'in senkron HTTP yerine job'a atılması, `max_workers=1`.
- Sunucu-üretimi dosya yolları.
- `INRES3_CONFIG` env override deseni (Docker ile tek fark host'lar).
