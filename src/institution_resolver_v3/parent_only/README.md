# Parent-only mod (yalniz kurum)

Serbest metin ifadeden **yalniz parent (kurum)** kaydini cozer; subunit hic
aranmaz, hic dondurulmez. Girdi formati degismez — sorgu yine kirli ve serbest
metindir (`"kurum + birim"` ya da yalniz kurum). Degisen tek sey ciktidir.

> Bu paket mevcut parent+subunit sisteminin bir **varyanti degil, yaninda duran
> ikinci bir moddur**. Bagimlilik TEK YONLU: `parent_only` cekirdegi import eder,
> cekirdekte `parent_only`'e giden **hicbir referans yoktur**. Bu yuzden burada
> ne yapilirsa yapilsin ana sistemin davranisi degisemez.
>
> Kararlarin gerekcesi ve tam olcum dokumu: [`__init__.py`](__init__.py) docstring'i.
> Bu dosya nasil kullanilacagini anlatir.

## Neden "mevcut sistem eksi subunit" degil

Parent karari **alt katmanlarda zaten subunit'ten bagimsiz**: `resolve._parent_union`
subunit aramasindan once ve ondan bagimsiz calisir, `gate._decide_pool` yalniz
parent havuzuna bakar. Subunit'in parent cevabina karistigi tek yer **ust yari**:

- `decide._needs_llm` — parent `auto_match` **olsa bile** subunit auto degilse
  sorgunun tamami hakeme gider ve hakem parent'i **ezebilir**.
- `judge()` — tek cagrida ikisine birden karar verir; subunit aday listesi baglamdadir.

Yani mevcut boru hattini calistirip ciktidan subunit'i silmek **ayni parent
cevabini vermez**. Paket bu yuzden kendi yonlendirme ve hakem katmanini tasir.

## Uc mod

| Mod | Ne yapar | LLM'e dusen satir |
|---|---|---|
| `gate` | LLM hic cagrilmaz; karar gate'in | %0 (~%61'i `auto_match`) |
| `hybrid` | gate `auto_match` vermezse hakeme devreder (**varsayilan**) | ~%38 |
| `llm` | her satir hakeme gider; gate yine hesaplanir (yalniz denetim icin) | %100 |

Gate sonucu **hangi yoldan gecerse gecsin** sonuca ve CSV'ye yazilir —
`decided_by=judge` olan satirlarda bile "gate ne dusunuyordu" denetlenebilsin diye.

## Kullanim

Kurulum ana repoyla ayni (`pip install -e ".[dev,embed,llm,api]"`); indeksleme
adimlari da aynidir, ayri bir index gerekmez.

### CLI — `inres3-parent`

```bash
inres3-parent match  "gazi üniversitesi mühendislik fakültesi"   # ES parent adaylari + ham skorlar
inres3-parent gate   "gazi üniversitesi mühendislik fakültesi"   # deterministik triyaj (LLM yok)
inres3-parent decide "gazi üniversitesi mühendislik fakültesi" --mode hybrid
inres3-parent batch  girdi.csv --query-col raw_name --out output/parent_sonuc.csv \
                     --mode hybrid --resume --workers 4
```

Ortak secenekler: `--top N` (aday sayisi), `--mode gate|hybrid|llm`,
`--model TAG` (Ollama tag'i), `--max-span N` (asagi bak), `--limit`, `--resume`,
`--workers` (IO-bound, varsayilan sirali).

### API — `inres3-parent-serve`

**Port 8001** ve `inres3-serve` ile **ayri import agaci** — burada bir hata
`inres3`'u kilitlemez (kasitli, 2026-08-04).

| Endpoint | Ne |
|---|---|
| `POST /parent/match`, `/parent/gate`, `/parent/decide` | tek sorgu |
| `POST /parent/batch` | CSV yukle, is baslat |
| `GET /parent/jobs`, `/parent/jobs/{id}`, `/parent/jobs/{id}/result` | is listesi, durum, sonuc CSV'si |
| `GET /health` | servis + ES durumu |

## Ayarlar

`config/default.yaml`'da **opsiyonel** bir `parent_only:` blogu. Blok yoksa her
deger makul bir varsayilana duser — yani `config/default.yaml` **degistirilmeden**
calisir (bu modun kurali: mevcut dosyalara dokunma).

```yaml
parent_only:
  garbage_lexical_floor: 0.55   # yoksa gate.garbage_lexical_floor, o da yoksa 0.55
  max_span: null                # null = sinirsiz (varsayilan)
  max_candidates: 8             # hakeme giden aday listesi ust siniri (havuz etkilenmez)
  generic_name_threshold: 3     # jenerik-ad korumasi; 0 = kapali
```

**`generic_name_threshold`** — gate'in karar omurgasi `exact_match` ve auto icin
`MIN_EXACT_SPAN=2` sarti var, ama bu eslesmenin **uzunlugunu** olcer,
**ayirt-ediciligini** degil. Sonuc: `"Gaziantep Sehitkamil State Hospital"`
sorgusunda katalogdaki jenerik `State Hospital` kaydi span=2 exact alip
`auto_match` cikiyordu. Adi katalogda bu esik kadar (>=) baska kayit adinin
icinde gecen aday artik auto olamaz, hakeme gider. Olculdu (460 satir): esik 3'te
11 supheli auto'nun 10'u yakalaniyor, bedeli 6 ek LLM cagrisi (%38.0 -> %41.5).
Esik 1 kullanilamaz (96 satir yonlendirir — neredeyse her Turk universitesi c=1 alir).

**`max_span`** — `decompose` sorgunun her ardisik kelime penceresini dener
(n kelime -> n(n+1)/2 pencere) ve parent-only surenin ~%57'si burada gecer.
Varsayilan `null` (sinirsiz) cunku uctan uca tabloda gorunmuyor: hibrit modda
40 ms kazanc, 7 saniyenin yaninda %0.5. **Yalniz `gate` modunda anlamli**
(438K satirda ~33 saat -> ~28 saat). Veriden: parent ad varyantlarinin %95.5'i
<=8, %99.5'i <=16 token; sorgular ortalama 7.6 kelime.

## Olculenler

Canli ES + `gemma4:e4b`, `benchmark_500_sample`, 2026-08-05:

| | Cekirdek | Parent-only |
|---|---|---|
| gate parent karari | — | **460/460 birebir ayni** |
| LLM'e dusen satir | %57.6 | **%38.3** |
| resolve | 0.49 s/sorgu | **0.27 s/sorgu** |
| hakem prompt'u | 8184 karakter | **2384 karakter** (%71 kucuk) |
| hakem cagrisi (N=6) | ~62 s | **~18 s** |
| uctan uca (hibrit) | ~35 s/satir | **~7 s/satir** |

Cekirdegin 500'luk kosusundaki 40 hatanin **30'u parent/subunit tutarsizligiydi** —
bu hata sinifi burada yapisal olarak imkansiz.

## Denenip REDDEDILENLER (tekrar denenmesin)

| Deney | Sonuc |
|---|---|
| `decompose`'u atmak | %75 hizli **ama** N=100'de 13 karari bozdu (auto 62 -> 56; kaybedilenler DOGRU cevaplardi). Girdi kirli oldugu icin kurum sinirini bulmak hala gerekli. |
| kNN'i atmak | %11 hizli, N=150'de 3 karar degisti. Vektorler kNN retrieval'da KALIR — capraz-dil recall'un kaynagi orasi. |
| Span sinirlamasi (varsayilan olarak) | Uctan uca %0.5 — LLM baskin oldugu icin anlamsiz. Secenek olarak kaldi, varsayilan degil. |
| "Hangi parent" ikilemi icin ozel kural | Gerekmedi: 500 sorguda ikilem 8 sorguda (%1.6) olusuyor ve **8/8'inde gate zaten `ambiguous`** diyor (parent'taki katil coklu-exact kurali). Sessizce yanlis seviyeye auto verilmiyor. |

Kosinus **geri-doldurma** yapilmaz: kNN listesine giren adaylar kosinusu ES
skorundan almaya devam eder (bedava), listeye girmeyenler icin sorgu-basina
~7 mget cagrisi atlanir. Bu deger ne gate karara katiliyordu ne prompt
gosteriyordu — hicbir kararin girdisi olmayan bir is yapiliyordu (N=150'de
150/150 ayni karar).

## Dosyalar

| Dosya | Ne |
|---|---|
| `__init__.py` | **karar gerekceleri + tam olcum dokumu** (once burayi oku) |
| `resolve.py` | parent havuzu (subunit aramasi ve kosinus geri-doldurma yok) |
| `gate.py` | deterministik triyaj — `gate._decide_pool` aynen import edilir, mantik kopyalanmaz |
| `genericity.py` | ad ayirt-ediciligi (jenerik-ad korumasi) |
| `judge.py`, `prompt.py`, `schema.py` | parent-only hakem katmani ve sema-kisitli cikti |
| `decide.py` | uc mod ve yonlendirme kurali |
| `batch.py` | CSV batch — `eval/csv_runner.py` aynen yeniden kullanilir |
| `cli.py`, `api.py` | `inres3-parent` ve `inres3-parent-serve` yuzeyleri |
| `config.py` | opsiyonel `parent_only:` blogu + varsayilanlar |

Testler: `tests/unit/test_parent_only.py`, `tests/unit/test_parent_only_api.py`
(ES/LLM'e cikmaz, olu ES ile de ayni surede gecer).
