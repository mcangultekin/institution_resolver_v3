# judge/ + decide/ — analiz (2026-07-29)

Kapsam: `judge/schema.py`, `candidates.py`, `prompt.py`, `client.py`, `judge.py`,
`decide/decide.py`.

Kanıt: **[Ö]** ölçüldü · **[K]** kod okumasıyla kesin · **[V]** muhakeme.

---

## 1. Rol ve genel değerlendirme

`judge/` = Aşama-2 LLM hakem (Gemma 4 E4B, yerel Ollama). `decide/` = gate ile
hakem arasındaki hibrit yönlendirici.

**Bu katman projenin en çok canlı-ölçümle şekillenmiş bölümü** ve bu görülüyor.
Her tasarım kararının arkasında somut bir hata vakası var:

| Karar | Çözdüğü canlı hata |
|---|---|
| `build_format_schema` (kısıtlı üretim, aday enum'ları) | model parent alanına subunit id'si yazıyordu (105863) |
| `_label_views` (P1../S1.. sentetik etiket) | E2B benzeyen rakamsal id'leri karıştırıyordu (152078 → 152062) |
| `_choice`'a `best_alias` eklenmesi | çapraz-dil: model `unit_phrase`'e İngilizce yazıp Türkçe-adlı yanlış adaya gidiyordu |
| `_trim` (8 aday) + exact garanti | 18 adaylı havuzda model 15. sıradaki alakasız adayı seçiyordu |
| `_trim`'in **sırayı bozmaması** | exact'leri öne taşımak, 1. sıradaki doğru adayı geriye itiyordu |
| `num_ctx` açıkça gönderilmesi | Ollama 2048 penceresini sessizce kırpıyordu, doğru cevap modele hiç ulaşmıyordu |
| kalıcı `httpx.Client` | her çağrıda yeni bağlantı ~5-8 s gizli maliyet ekliyordu |
| sabit blok başta, değişken veri sonda | KV-cache 2. satırda kırılıyor, 1.5k token'lık talimat yeniden işleniyordu |
| `reasoning` alanının kaldırılması | ~200 token → ~10-20 token üretim |
| kosinüsün prompt'tan çıkarılması | e5 anizotropik, tüm benzerlikler ~[0.74, 0.87]'de sıkışık |

Ayrıca **hatalar yutulmuyor**: `JudgeValidationError` / `LlmError` API'de 502,
CLI'da exit 1, batch'te `status=error` olarak yüzeye çıkıyor. `_validate_ids`
halüsinasyonu şema desteği olmayan client'lar için ikinci kemer olarak duruyor.
`OllamaClient` prompt kırpılmasını `prompt_eval_count` ile tespitip **hata
fırlatıyor** — sessiz yanlış karar üretmektense patlamayı seçmiş. Bu doğru
refleks.

---

## 2. Eksikler

### J1 — Üretim şeması, doğrulama şemasından ZAYIF: kendi hatasını davet ediyor **[K]**

`build_format_schema` her karar bloğunu şöyle tanımlıyor:

```python
{"verdict": {"enum": ["auto_match","review","ambiguous","no_match"]},
 "matched_id": {"anyOf": [{"enum": choices}, {"type": "null"}]}}
```

Bu şemaya göre `{"verdict": "auto_match", "matched_id": null}` **tamamen
geçerli** bir üretim. Ama `judge/schema.py`'nin `_matched_id_consistency`
validator'ı tam olarak bunu reddediyor:

> `'auto_match' dedi (bir eşleşme var) ama hangi kayda eşleştiğini belirtmedi - çelişkili`

Yani kısıtlı üretimin bütün amacı ("model şema dışına **fiziksel olarak**
çıkamasın") bu alanda çalışmıyor: modelin üretebildiği bir çıktı, bizim
reddettiğimiz bir çıktı. Bu, gözlemlenen `JudgeValidationError`'ların bir
bölümünün doğrudan kaynağı olabilir.

**Düzeltme:** çapraz-alan kısıtını şemaya kodla —

```python
{"anyOf": [
  {"properties": {"verdict": {"const": "no_match"}, "matched_id": {"type": "null"}}, ...},
  {"properties": {"verdict": {"enum": ["auto_match","review","ambiguous"]},
                  "matched_id": {"enum": choices}}, ...}]}
```

Böylece çelişkili çıktı üretim aşamasında imkânsız hale gelir — projenin
`_decision_schema` docstring'inde savunduğu ilkenin ta kendisi.

### J2 — Aday listesi boşken şema ÇELİŞKİYE ZORLUYOR **[K]**

```python
matched = {"anyOf": [{"enum": choices}, {"type": "null"}]} if choices else {"type": "null"}
```

`choices` boşsa `matched_id` zorunlu `null`, ama `verdict` enum'u hâlâ dört değeri
de kabul ediyor. Model `auto_match`/`review`/`ambiguous` derse — ki boş listede
bunu demesi için bir sebep yok ama küçük model bunu yapabilir — çıktı **kesin
olarak** pydantic'te patlar. Aday yoksa `verdict` `{"const": "no_match"}` olmalı.

### J3 — `_trim` üst sınırı aşabiliyor; prompt boyutu veriye bağlı **[Ö/K]**

```python
keep_ids = {v.id for v in views if v.exact_match}   # önce TÜM exact'ler
```

Exact sayısı `max_candidates`'i (8) aşarsa fonksiyon 8'den **fazla** aday
döndürüyor — "güçlü kanıt hiçbir zaman dışarı atılmaz" ilkesinin bilinçli
sonucu. Ama bu ilkeyi bir veri gerçeğiyle birlikte okumak gerekiyor:

**Subunit kayıtlarının %79'u** (98.816 / 125.108) en az bir başka kayıtla aynı
normalize ada sahip (`rektorluk` ×216, `psikoloji bolumu` ×181 — ölçüm
`01_gate.md` C1). Yani "çok sayıda eşit exact" bu korpusta istisna değil, norm.

Zincir: çok exact → `_trim` şişer → prompt büyür → `num_ctx=8192` aşılır →
`OllamaClient` `LlmError` fırlatır → satır `status=error`. Yani **bir veri
özelliği, çalışma zamanı hatasına dönüşüyor.** Hata en azından sessiz değil
(iyi), ama sınırlanmamış bir üst sınır üretimde patlama demek.

**Öneri:** exact'ler için de bir tavan koy (ör. 2×`max_candidates`), aşımda
`passed_parent_filter` / sıralama ile kırp ve kırpıldığını `signals`'a yaz.

### J4 — `_trim`'in döngü koşulu no-op **[K]**

```python
if len(keep_ids) >= max(max_candidates, len(keep_ids)):
    break
```

`len(keep_ids) < max_candidates` ise `max(...)` = `max_candidates`;
değilse koşul `x >= x` yani hep doğru. Sonuç `if len(keep_ids) >= max_candidates`
ile **birebir aynı**. Davranış doğru, ifade gereksiz dolambaçlı — bu satırı
okuyan bir sonraki kişi (ya da model) burada olmayan bir incelik arayacak.

### J5 — Doğrulama sonrası model mutasyonu **[K]**

```python
result.parent.matched_id = _to_real(result.parent.matched_id, p_map)
```

`JudgeResult.model_validate(...)`'dan **sonra** alan atanıyor. Pydantic v2'de
`validate_assignment` açık olmadığı için `_matched_id_consistency` yeniden
çalışmıyor. Şu an güvenli (etiket→id çevirisi `None`'luğu korur), ama sözleşme
tip sistemiyle değil dikkatle tutuluyor. `model_copy(update=...)` ya da
çeviriyi `model_validate` **öncesine** almak riski sıfırlar.

### J6 — Kosinüs artık kimsenin kararına girmiyor ama hâlâ pahalı hesaplanıyor **[K]**

Kosinüs 2026-07-27'de prompt'tan çıkarıldı (haklı gerekçe). Ama:
- `resolve._default_cosine_fn` hâlâ kNN top-K'ya girmeyen **her aday için**
  kosinüs hesaplıyor (`encode_query` + gerekirse `fetch_embeddings` **mget**),
- `CandidateView.cosine` hâlâ taşınıyor,
- gate `signals`'ta yalnız gösteriyor.

Yani karar verici hiçbir tüketicisi kalmamış bir sinyal için, sorgu başına
ekstra ES round-trip'i ödeniyor. DURUM §8 madde 5 bunu zaten açık iş olarak
yazmış ("*Bu oturumda YAPILMADI*") — hâlâ açık. kNN **retrieval'da** kalmalı
(çapraz-dil recall'ün asıl değeri orada); geri-doldurma yolu atılabilir.

### J7 — `judge.enabled` ve `judge.cache_dir` config anahtarları ölü **[Ö]**

- `judge.enabled: false` — `src/` içinde **hiç okunmuyor** (grep: 0 hit). Batch
  komutu hakemi doğrudan çağırıyor. Yani "hakem kapalı" ayarı hiçbir şeyi
  kapatmıyor. DURUM §6c bunu not etmiş, düzeltilmemiş.
- `judge.cache_dir: "llm_cache"` — okunmuyor, **LLM yanıt cache'i yok**.
  30–50 s/sorgu maliyetinde ve tekrarlı sorgu içeren batch'lerde (438k satırlık
  girdide tekrar beklenir) bu ciddi bir kayıp. Config özelliğin var olduğunu ima
  ediyor, kod yok.

### J8 — LLM hatası, elde olan gate cevabını da yok ediyor **[K]**

`decide()` gate yetmediğinde `judge_fn`'i çağırıyor; hakem patlarsa istisna
yukarı çıkıyor → API 502, CLI exit 1, batch `status=error`.

Ama `DecideResult.gate` her zaman doluydu — gate'in bir görüşü **vardı**
(`review`, `ambiguous`, hatta bir `matched_id` önerisi). LLM erişilemediği için
bu deterministik bilgi de çöpe gidiyor. DURUM §7 bunu açık borç olarak yazmış:

> decide/ katmanı … doğrulama reddi olduğunda otomatik tekrar deneme /
> review'e düşürme yok.

**Öneri:** `decide()`'a `on_judge_error: "raise" | "fallback_to_gate"` politikası.
Fallback'te sonuç gate'in kararı + `decided_by="gate_fallback"` + hata mesajı
`signals`'ta. Üretimde "hiç cevap yok" yerine "düşük güvenli cevap + neden"
neredeyse her zaman daha iyi.

### J9 — Tekrar deneme (retry) hiçbir katmanda yok **[K]**

`temperature=0.0` olduğu için aynı prompt aynı çıktıyı verir — naif retry
faydasız, doğru. Ama şema/format hatasında **prompt'u küçülterek** (aday sayısını
azaltarak) tekrar denemek anlamlı olurdu, özellikle J3'teki num_ctx aşımında
(`LlmError` mesajı zaten "aday listesini küçültün" diyor — ama bunu kimse otomatik
yapmıyor).

### J10 — Test boşluğu **[Ö]**

`judge/schema.py` testlerde hiç import edilmiyor. Validator'lar (`no_match ⟺
matched_id`, int→str, `"null"`→None) sistemin en ince mantığından biri ve
doğrudan test edilmiyor — yalnız `test_judge.py` üzerinden dolaylı kapsanıyor.
J1/J2 tam olarak bu validator'ların şemayla uyuşmadığı yer.

---

## 3. Öneriler (öncelik sırasıyla)

| # | İş | Neden | Maliyet |
|---|---|---|---|
| 1 | **J1+J2** şemaya çapraz-alan kısıtı | üretilen çelişkili çıktıyı fiziksel olarak imkânsız kılar | ~15 satır |
| 2 | **J8** gate'e fallback politikası | LLM hatası deterministik cevabı yok etmesin | ~20 satır |
| 3 | **J3** exact tavanı | veri özelliğinin runtime hatasına dönmesini engeller | ~10 satır |
| 4 | **J7** `judge.enabled` bağla + LLM cache | ölü ayar + 30-50 s/sorgu tasarrufu | orta |
| 5 | **J6** kosinüs geri-doldurmayı kaldır | sorgu başına gereksiz ES round-trip | küçük |
| 6 | **J10** `schema.py` birim testleri | J1/J2'nin yaşadığı yer | küçük |
| 7 | **J4/J5** kozmetik/sağlamlaştırma | okunabilirlik + tip güvenliği | küçük |

## 4. Değiştirilmemesi gerekenler

- Kısıtlı üretim + sentetik etiketler + `best_alias`'ın enum değerine gömülmesi.
- `_trim`'in **sırayı korunması** (exact'leri öne taşımama).
- Ham metin ilkesi (prompt'ta `unit_part` gösterilmemesi).
- `reasoning` alanının kaldırılmış olması ve kosinüsün prompt'ta olmaması.
- Sabit-blok-başta prompt düzeni (KV-cache).
- `num_ctx`'in açıkça gönderilmesi + kırpılma tespiti.
- Hataların yutulmaması — yalnızca J8'deki *politika* eklenmeli, sessizleştirme
  değil.
