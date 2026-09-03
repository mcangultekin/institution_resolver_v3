# Institution Resolver v3

Serbest metin kurum ifadesini (`"gazi üniversitesi mühendislik fakültesi makine
mühendisliği"`) kanonik **parent** + **subunit** kayitlarina cozer.
Aday uretimi **Elasticsearch**'te; nihai karar bir **LLM hakem katmaninda**
(yerel Gemma / Ollama — Claude/Anthropic bu katmanda kullanilmaz, maliyet karari).

> v2 (`../institution_resolver_v2`) referans olarak yaninda durur. v3 onun
> kodundan **import etmez**; kanitli parcalar (normalize, akronim kurallari,
> batch iskeleti) buraya kopyalanir.
>
> **Guncel durum, alinan kararlar ve yol haritasi: [`docs/DURUM.md`](docs/DURUM.md).**
> Bu README arayuz belgesidir (ne var, nasil calistirilir); tarihce oraya yazilir.

## Cikti sozlesmesi

Her sorgu icin tek JSON: `parent` + `subunit` (her biri `decision` +
`confidence` + `merged_ids`) + `evidence`. Karar etiketleri:
`auto_match` / `review` / `ambiguous` / `no_match` (`no_match` birinci sinif).
`auto_match` icin gercek sette kesinlik hedefi **>= %98**.

## Mimari

```
INDEKSLEME (offline):
  raw CSV -> ingest/canonicalize -> embedding -> elastic (tek index + force-merge)

SORGU:
  normalize -> elastic.search (parent + subunit havuzlari, ham skorlar)
            -> retrieve.signals -> gate (deterministik) -> judge (LLM) -> decide
```

- **ES'in isi** aday bulmak, **LLM'in isi** adaylar arasindan secmek.
- Katmanlar ayri paket (`retrieve/ gate/ judge/ decide/`), birbirine sizmaz.
- Gate LLM'siz triyaj yapar: kolaylari ve copu ayirir, kalan satirlar hakeme gider.
- Katman sorumluluklari icin her paketin `__init__.py` docstring'ine bak.

## Dizin haritasi

| Yol | Ne |
|---|---|
| `src/institution_resolver_v3/` | paket: `ingest/ normalize/ embedding/ elastic/ retrieve/ gate/ judge/ decide/ eval/ api/ cli/` |
| `config/default.yaml` | tum ayarlar (ES, retrieval, embedding, gate, judge, decision) |
| `config/docker.yaml` | container ici host adlari (`INRES3_CONFIG` ile secilir) |
| `data/raw/` | ham `institution_parent.csv` / `institution_subunit.csv` (versiyonlanmaz) |
| `data/processed/` | kanonik JSONL + `embeddings.npz` + `transform_report.json` |
| `data/eval/` | degerlendirme setleri (gercek sorgular — **commit edilmez**) |
| `output/` | kosu ciktilari ve loglar (**commit edilmez**; ozetleri `docs/RAPOR_*.md`) |
| `docker-compose.yml` | ES + Ollama + API (bkz. `DOCKER_README.md`) |
| `notebooks/colab_e2e.ipynb` | ayni akis Colab'da (GPU, Docker yerine native process) |
| `scripts/` | tek seferlik yardimcilar (benchmark siniflama, gold etiketleme) |
| `tests/unit/` | pytest; `integration` ve `llm` marker'lari canli servis ister |

## Kurulum

```bash
pip install -e ".[dev,embed,llm,api]"
inres3 --help
```

Ekstra gruplar: `embed` (sentence-transformers, kNN), `llm` (httpx, Ollama
istemcisi), `api` (FastAPI servisi), `dev` (pytest).

Servisler:

```bash
docker compose up -d
```

`entrypoint.sh` ilk acilista Ollama modelini otomatik indirir ve `data/processed/`
mevcutsa indeksleme adimini kendisi calistirir; detay icin `DOCKER_README.md`.

## Indeksleme (offline, bir kez)

```bash
inres3 build-data --raw-dir data/raw --out-dir data/processed   # ham CSV -> kanonik JSONL + rapor
inres3 setup-es                                                 # index + mapping
inres3 index --embeddings                                       # belgeleri + e5 vektorlerini yukle
```

`--recreate` mevcut index'i siler ve sifirdan kurar (varsayilan: uzerine yazar).

## Sorgu komutlari

Her biri ardisik bir katmani acar; hepsi tek sorgu alip terminale yazar.

```bash
inres3 match  "gazi üniversitesi istatistik bölümü"    # sadece ES aday havuzu + ham skorlar
inres3 gate   "gazi üniversitesi istatistik bölümü"    # + deterministik triyaj karari
inres3 judge  "gazi üniversitesi istatistik bölümü"    # + LLM hakem ciktisi (sema-kisitli)
inres3 decide "gazi üniversitesi istatistik bölümü"    # tam boru hatti -> nihai karar
```

Ortak secenekler: `--top N` (her havuzdan aday sayisi), `--model TAG`
(config'deki `judge.model` yerine baska bir Ollama tag'i).

## Batch

CSV alir, sonuc CSV'si yazar; `--resume` ile kaldigi yerden devam eder
(no_match/review/ambiguous ve hatalar satir olarak korunur).

```bash
inres3 gate-batch   girdi.csv --query-col raw_name --out output/gate_sonuc.csv --resume
inres3 decide-batch girdi.csv --query-col raw_name --out output/decide_sonuc.csv --resume --workers 4
inres3 batch        girdi.csv --query-col raw_name --out output/batch_sonuc.csv --resume
```

`gate-batch` LLM'siz (hizli triyaj), `decide-batch` gate + hakem, `batch`
resolve + hakem. `--workers` yalniz `decide-batch`'te ve LLM'e dusen satirlar
icindir (varsayilan sirali).

> Batch ciktilari sorgu metnini satir satir tasir, yani gercek affiliation
> verisidir. `output/` ve `*_sonuc.csv` bu yuzden `.gitignore`'dadir.

## HTTP servisi

```bash
inres3-serve            # ya da: docker compose up -d api
```

| Endpoint | Ne |
|---|---|
| `GET /` | kucuk demo arayuzu (`api/static/index.html`) |
| `GET /health` | servis + ES durumu |
| `GET /docs` | OpenAPI |
| `POST /match`, `/gate`, `/decide` | tek sorgu |
| `POST /batch/gate`, `/batch/judge`, `/batch/decide` | CSV yukle, is baslat |
| `GET /jobs`, `/jobs/{id}`, `/jobs/{id}/result` | is listesi, durum, sonuc CSV'si |

Yuklenen CSV'ler ve ciktilar `data/jobs/` altinda tutulur (kullanici verisi,
versiyonlanmaz).

## Ayarlar

Tek kaynak `config/default.yaml`. `INRES3_CONFIG` ortam degiskeni baska bir
dosyaya isaret edebilir (container'da `config/docker.yaml`). API portu `PORT`
ile degistirilir.

Kural: **bir anahtar dosyada var diye davranis degistirmez** — okunmayan olu
anahtar birakilmaz (v2 O6 dersi). Her anahtarin yanindaki yorum, o degerin
neden oyle oldugunu (hangi deney/karar) soyler.

## Testler

```bash
pytest                                  # birim testleri
pytest -m integration                   # canli ES ister (docker compose up)
pytest -m llm                           # canli Ollama ister
```

## Belgeler

| Dosya | Ne |
|---|---|
| [`docs/DURUM.md`](docs/DURUM.md) | **guncel durum, alinan kararlar, yol haritasi** |
| `docs/V3_BASLANGIC_REHBERI.md` | tasarim dayanagi ve faz plani (F0–F5) |
| `docs/V3_VERI_PLANI.md` | kanonik veri modeli, merge/klon kurallari |
| `docs/UYGULAMA_KILAVUZU.md` | uygulama ilkeleri |
| `docs/29_temmuz_analizler/` | katman katman sistem analizi (`00_OZET.md` ile basla) |
| `docs/DENEY_*.md`, `docs/RAPOR_*.md` | tekil deney ve olcum raporlari |
| `docs/FABLE_RETROSPEKTIF.md`, `docs/DURUM_2026-07-27.md` | tarihce |
