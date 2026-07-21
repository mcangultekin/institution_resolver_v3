# Institution Resolver v3

Serbest metin kurum ifadesini (`"gazi üniversitesi mühendislik fakültesi makine
mühendisliği"`) kanonik **parent** + **subunit** kayitlarina cozer.
Aday uretimi **Elasticsearch**'te; nihai karar bir **LLM hakem katmaninda**.

> v2 (`../institution_resolver_v2`) referans olarak yaninda durur. v3 onun
> kodundan **import etmez**; kanitli parcalar (normalize, akronim kurallari,
> batch iskeleti) buraya kopyalanir. Tasarim dayanagi: `docs/`.

## Cikti sozlesmesi

Her sorgu icin tek JSON: `parent` + `subunit` (her biri `decision` +
`confidence` + `merged_ids`) + `evidence`. Karar etiketleri:
`auto_match` / `review` / `ambiguous` / `no_match` (`no_match` birinci sinif).

## Mimari

```
INDEXLEME (offline):
  raw CSV -> ingest/canonicalize -> embedding -> elastic (tek index + force-merge)

SORGU:
  normalize -> elastic.search (parent + subunit havuzlari, ham skorlar)
            -> retrieve.signals -> gate (deterministik) -> judge (LLM) -> decide
```

Katman sorumluluklari icin her paketin `__init__.py` docstring'ine bak.

## Insa sirasi (bkz. docs/V3_BASLANGIC_REHBERI.md, konusulan revizyonla)

| Faz | Is |
|---|---|
| F0 | Kanonik veri (JSONL) + 400 gercek etiket (ayar/kabul ayri) |
| F1 | Tek-index ES + hibrit arama, ham skorlar, determinizm gun-1 |
| F2 | **Gercek sette recall@50 olc** - darbogaz retrieval mi karar mi? |
| F3 | LLM'i her seye kos (tek cagri parse+judge), tavani olc |
| F4 | Yetki asimetrisi + deterministik gate'i maliyet icin ekle |
| F5 | Batch (resume/memoization) + cikti + EXPERIMENTS v3 gunlugu |

## Komutlar (fazlar ilerledikce dolar)

```bash
pip install -e ".[dev]"
inres3 version                                    # iskelet dogrulamasi
cd docker && docker compose up -d && cd ..        # ES ayaga kalkar (F1)
```

## Durum

Iskelet kuruldu (dizin yapisi + tasinan moduller: `models.py`, `normalize/text.py`,
`ingest/raw_loader.py`). Kanonik veri `data/processed/` altinda. Kod fazlari
henuz baslamadi.
