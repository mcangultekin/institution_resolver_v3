# Gate katmanı — derin analiz raporu (2026-07-29)

Kapsam: `gate/gate.py`, tükettiği `retrieve/resolve.py` sinyalleri, `decide/decide.py`
ile etkileşimi, `eval/gate_batch.py`, `tests/unit/test_gate.py`. Ölçümler
`data/processed/*.jsonl` (106.183 parent / 125.108 subunit) üzerinde yapıldı.
Durum: 191/191 test geçiyor, branch `feat/gate-asama1`.

Kanıt seviyeleri: **[Ö]** = bu oturumda veriyle/kodla ölçüldü, **[K]** = kod
okumasıyla kesin, **[V]** = varsayım/muhakeme (ölçülmedi).

> **2026-07-30 güncellemesi — parent'ta çoklu exact kuralı sıkılaştı.**
> Aşağıdaki karar ağacındaki "eşit-uzun ikinci exact var → ambiguous" satırı
> artık **yalnızca subunit için** geçerli. **Parent'ta HERHANGİ ikinci güçlü
> exact** `auto_match`'i engelliyor (span farkına bakılmıyor; reason
> `coklu_exact_herhangi`). Kullanıcı kararı; ölçülen bedel benchmark'ın ilk 150
> sorgusunda 5 karar (%3.3) auto→ambiguous, hakeme giden sorgu +%2.0, 1 subunit
> kararı `_enforce_coherence` üzerinden review'e indi. Bu kural bir hata
> önlemiyor — 5 vakada bugünkü seçim doğru görünüyordu (rakipler kazananın
> içindeki jenerik alt-parçalardı: `İSTANBUL ÜNİVERSİTESİ-CERRAHPAŞA` karşısında
> `İSTANBUL ÜNİVERSİTESİ`) — "şüpheli auto yerine belirsizlik" risk tercihini
> uyguluyor. Geri alma: `gate()` içindeki `any_rival_blocks_auto=True` → `False`.
>
> Ayrıca parent **arama** kanalı da değişti (nested `alias_variants`, kanonik/alias
> ayrımı yok) — havuz kompozisyonu bu rapordaki ölçümlerden farklı. Bkz.
> `03_elastic_ve_embedding.md` ve `docs/DURUM.md`.

---

## 1. Gate bugün ne yapıyor

Tek girdi (`ResolveResult`) → iki bağımsız havuz (parent, subunit) → her biri için
`auto_match / review / ambiguous / no_match` + `confidence` + `signals`.

Karar omurgası tek sinyal: **`exact_match`** (aday adı/alias'ı sorguda ARDIŞIK
geçiyor mu). Kabaca:

```
havuz boş                                   -> no_match
güçlü exact (span>=2, çelişki yok) yok
    ├─ best_tsr < floor                     -> no_match
    └─ değilse                              -> review (matched_id=None)
güçlü exact var
    ├─ sorgu parçası kısa akronim           -> review
    ├─ ikinci exact var                     -> ambiguous
    │     parent : HERHANGİ ikinci exact (2026-07-30)
    │     subunit: yalnız eşit-uzun rakip
    └─ tek                                  -> auto_match
subunit: parent'a bağlanır (prefer_parent_id) + _enforce_coherence ile down-cap
```

`bm25_norm` ve `cosine` bilinçli olarak karardan çıkarılmış, yalnız `signals`'ta
taşınıyor.

### Doğru bulduğum tasarım kararları
- **Tek sinyalli omurga.** bm25 (sorgu-içi göreli) ve kosinüs (anizotropik)
  gerekçeleri sağlam ve kanıtlıydı; N=200'de %79 ambiguous → %58 temiz auto
  dönüşümü ciddi bir kazanım.
- **`_enforce_coherence`** doğru yönde asimetrik: yalnız down-cap, promosyon yok,
  `matched_id` öneri olarak korunuyor. Regresyon testi de var.
- **Saf fonksiyon** (ES/LLM yok, config enjekte edilebilir) → test edilebilirlik
  yüksek, blast-radius küçük.
- Ölü kod yok, `signals` denetim için eksiksiz CSV'ye akıyor.

---

## 2. Eksikler

### A. Karar mantığındaki kesin hatalar / tutarsızlıklar

#### A1 — `confidence` iki farklı formülle üretiliyor **[K]**

`gate.py:144,148` (review/no_match dalları) `confidence = best_tsr/100` yazıyor;
`gate.py:158` (exact dalı) `score_candidate(best)` çağırıyor. Yani aynı alan
bazen ham tsr, bazen exact-bonuslu/çelişki-cezalı skor. Sonuç: `confidence`
kovalar arası **karşılaştırılamaz**, eşik takılamaz. `score_candidate`'in
docstring'i "yalnız `confidence` alanı için" diyor ama çağrıların yarısında
atlanıyor.

#### A2 — `no_match` tabanı fiilen ölü; review sinyalleri yanlış adayı gösteriyor **[Ö]**

`token_set_ratio`, adayın tokenleri sorgunun **alt kümesiyse 100 döner**. Ölçüm:

```
sorgu: "calcutta institute of engineering and management department of
        computer science kolkata india"
  aday "india"                          -> tsr = 100.0
  aday "management"                     -> tsr = 100.0
  aday "indian institute of technology" -> tsr =  57.1
```

Bunun üç ayrı sonucu var:

1. `best_tsr = max(tüm havuz)` olduğu için **tek bir kısa/jenerik çöp aday tabanı
   şişiriyor** → `garbage_lexical_floor` neredeyse hiç ateşlemiyor. Baseline'da
   parent `no_match` = 1/50 (%2). Yani "çöp kapısı" diye bir kapı yok.
2. `display = max(candidates, key=tsr)` olduğu için review/no_match satırlarında
   `signals`'a yazılan tsr/bm25/cosine **"india" adayına ait**, makul adaya değil.
   Denetim kolonları sistematik olarak yanlış kaydı gösteriyor.
3. `confidence` o dalda `best_tsr/100` olduğundan böyle bir review satırı
   **confidence = 1.000** ile çıkıyor.

Not: DURUM §6e'de "tsr≥95 görünen 6 vaka TUZAK" diye gözlenen sınıf büyük
olasılıkla tam olarak budur — semptom doğru teşhis edilmiş ama kök neden
(`token_set_ratio`'nun alt-küme davranışı) `bm25_norm` için yazılan "sorgu-içi
göreli, çöp de 1.0 alıyor" gerekçesinin **birebir aynısı**; tsr için fark
edilmemiş.

#### A3 — exact + qualifier çelişkisi, "exact yok" gibi raporlanıyor **[K]**

`_is_strong_exact` çelişkiyi filtreliyor (`gate.py:66`), böyle bir aday
`exact` listesine hiç girmiyor → `reason="exact_yok"`. Oysa gerçek neden
"exact vardı ama nitelik çelişti". Denetimde bu ikisi ayırt edilemiyor ve
`test_conflict_exact_not_strong` yalnız `!= auto_match` doğruluyor. Ek olarak
A1 yüzünden o adayın çelişki cezası confidence'a **hiç yansımıyor**.

#### A4 — `review` + `matched_id=None`, hakem şemasına göre çelişkili bir durum **[K]**

`judge/schema.py` `_matched_id_consistency`: `verdict != "no_match"` ise
`matched_id` zorunlu. Gate'in `exact_yok` dalı tam olarak bunu ihlal eden bir
nesne üretiyor. Gate o validator'dan geçmiyor, ama modül docstring'i "hakemle
AYNI DİLDE" diyor — dil aynı değil. `decide/` ve API tüketicileri
"non-no_match ⇒ id var" varsayarsa sessizce kırılır.

#### A5 — akronim kontrolü adaya değil sorgu metnine bakıyor **[K]**

`_is_short_acronym(query_part)`, ham metin üzerinde `len<=5 and " " not in t`.
- `"M.E.T.U"` (7 karakter) → akronim sayılmaz.
- `"Bilgi"` (5 karakter, gerçek bir üniversite adının tamamı) → akronim sayılır,
  gereksiz review.
- Subunit tarafında `unit_phrase` kısa bir gerçek birim adıysa ("Tıp") yine
  gereksiz review.
Noktalama temizliği yok, kontrol adayın kendi formuna (tümü büyük harf mi,
katalogda akronim alias'ı mı) bakmıyor.

### B. Elde olan ama kullanılmayan kanıt (hepsi gate-lokal, resolve'a dokunmadan)

`ScoredCandidate` / `DecomposedQuery` gate'e şunları taşıyor ve **hiçbiri
okunmuyor**:

| Alan | Ne söylüyor | Neden değerli |
|---|---|---|
| `decomposed.hypotheses` | 5 sınır hipotezi + işaret ettikleri parent id'leri | **Mutabakat** bağımsız bir kanıt: exact ile aynı parent'ı gösteren N hipotez auto'yu güçlendirir; farklı parent'ları gösteriyorsa ambiguous'a çeker. Bedava. |
| `passed_parent_filter` | subunit cascade filtresinden mi geldi | "seçilen parent altında gerçekten bulundu" kanıtı; şu an `raw["parent_id"]` ile elle yapılıyor |
| `best_alias` | sorguya en yakın alias | Çapraz-dil köprüsü. DURUM §6e'nin kendi sonucu: "asıl değer #29'daki alias köprüsünde" |
| `raw["from_hypothesis_only"]` | aday hiçbir aramanın top-K'sına girmedi, enjekte edildi | Bu adaylar `bm25_norm=0, cosine=None` ile gelir ama `exact_match` hesaplanır → **hiçbir aramada bulunmamış bir kayıt auto_match alabilir** |
| `boundary_score` | decompose'un sınır güveni | Düşük sınır güveni = `institution_part`'a güvenme sinyali |

#### B1 — En kritiği: exact'in **ayırt ediciliği** ölçülmüyor, yalnız **uzunluğu** **[Ö]**

`MIN_EXACT_SPAN = 2` bir uzunluk eşiği. Ama span=2 jenerik de olabilir. Katalogda
tamamı jenerik kelimelerden oluşan (2-4 token) parent kayıtları:

```
17654  Centre College            57702  University Medical Center
26171  Medical Center Hospital   95330  University School
27541  College Medical Center    53034  Dali University
```

6 kayıt — az ama bunlar **çekim merkezi** sınıfı: "... University Medical Center,
Boston, MA" gibi bir sorgu span=3 exact ile `auto_match` alır. Gözlenen yanlış-auto
sınıfı ("Acıbadem Hastanesi" → şube) span=1'di; `MIN_EXACT_SPAN=2` bunu bir çentik
yukarı taşıdı, **sınıfı ortadan kaldırmadı**.

Aynı zamanda: **parent'ın `exact_match`'i TAM SORGUYA karşı hesaplanıyor**
(`resolve.py:323`, `_attach_signals(query_text=query)`) — `institution_part`'a
değil. Yani parent exact'i sorgunun **birim kısmından** ateş alabilir ve gate bunu
kontrol etmiyor: parent exact span'i ile subunit exact span'inin sorguda çakışıp
çakışmadığına, sorgunun ne kadarını açıkladığına bakılmıyor.

### C. Yapısal sorunlar

#### C1 — Subunit kesinliği yapısal olarak parent'a bağımlı **[Ö]**

Ölçüm: subunit kayıtlarının **%79'u** (98.816 / 125.108) en az bir başka kayıtla
aynı normalize adı paylaşıyor. En sık: `rektorluk` ×216, `bilgisayar
muhendisligi bolumu` ×190, `psikoloji bolumu` ×181.

Sonuç: `prefer_parent_id` daraltması **çalışmazsa** (parent `review` →
`matched_id=None`, ya da o parent altında exact yok) `rivals` kaçınılmaz olarak
ateşler → `ambiguous`. Yani subunit'in `ambiguous`'u bağımsız bir bilgi taşımıyor,
**parent'ın belirsizliğini tekrar ediyor**. Baseline'da subunit ambiguous'un
düşük görünmesi (1/50) gate'in iyi ayırt ettiği için değil, parent'ın %60 auto
olması ve cascade havuzunun zaten dar olması sayesinde.

Karşılık olarak parent'ta durum tersi: tekrarlı normalize parent adı yalnız
**3 ad / 6 kayıt (%0.01)** — parent tarafında "gerçek ikiz" gerçekten nadir, yani
parent `ambiguous`'u anlamlı.

#### C2 — Promosyon hiçbir yerde yok **[K]**

`_enforce_coherence` docstring'i promosyonu (güçlü subunit'in belirsiz parent'ı
netleştirmesi) bilerek `decide/`'a bırakıyor. Ama `decide.py` promosyon yapmıyor:
`_needs_llm` sadece bakıp her şeyi LLM'e atıyor. Devredilen sorumluluk devralınmamış.

#### C3 — Gate'in kova ayrımı maliyet tarafında karşılıksız **[K]**

`decide._needs_llm`: `auto_match` **dışındaki her şey** LLM'e gidiyor. Yani
`review`, `ambiguous` ve `no_match` maliyet açısından özdeş. Özellikle `no_match`
(gerçek çöp, ES havuzu boş ya da taban altı) LLM'e gitmemeli — hakem de aynı boş
havuzu görecek. Gate'in ürettiği 4-kova ayrımının şu an tek maliyet etkisi
"auto mı, değil mi" ikilisi.

### D. Ölçüm / kalibrasyon

- **Gold yok.** Kova *dağılımı* biliniyor (%60/%34/%4/%2), **doğruluk bilinmiyor**.
  `decision.auto_precision_target: 0.98` hedefi hiç ölçülmedi. Bu en büyük eksik:
  yukarıdaki A/B maddelerinin hangisinin gerçekte kaç vakayı bozduğu bilinmiyor.
  (v2'deki `real_labeled.csv` denendi; kullanıcı geçersiz ilan etti, silindi —
  2026-07-29. Gold sıfırdan üretilecek.)
- **Eval seti — GÜNCELLENDİ (2026-07-29).** 50 sorguluk set ve `gate_baseline.py`
  scratchpad ile birlikte **silindi**, kurtarılamadı. Yerine
  `data/eval/benchmark_500_sample.csv`: 500 benzersiz gerçek sorgu, çok eksenli
  kategorili (`kurum_tipi`/`sorgu_formu`/`dil`/`bozulma`) + 39 doğrulanmış
  `beklenen=no_match`. Baseline dağılımı bu sette **henüz koşulmadı** —
  aşağıdaki %60/%34/%4/%2 rakamları hâlâ eski 50 sorgudan.
- **Testler sentetik.** 13 gate testi elle kurulmuş `ScoredCandidate`'ler; hiçbiri
  A2'deki tsr alt-küme davranışını ya da jenerik-exact vakasını temsil etmiyor.
- `garbage_lexical_floor: 0.55` placeholder ve A2 yüzünden zaten etkisiz.

---

## 3. Öneriler (etki × risk sırasıyla)

### G1 — Ucuz düzeltmeler, davranış riski düşük (yarım gün)

1. **`confidence` tek formüle**: her dalda `score_candidate(...)`. review/no_match
   dalında `display` yerine kararı temsil eden adayı kullan.
2. **`reason` zenginleştir**: `exact_yok` → `celiski_var` / `span_kisa` /
   `exact_hic_yok` ayrımı. Sıfır davranış değişikliği, denetim değeri yüksek.
3. **`no_match`'i LLM'den muaf tut** (`decide._needs_llm`): havuz boş / taban altı
   ise hakem de bulamaz. Tek satır; asıl kazanç G2'den sonra gelir.
4. **Akronim kontrolünü normalize et**: noktalama sil, adayın katalog formuna bak.
5. **`from_hypothesis_only` adaylara auto verme** — hiçbir aramanın top-K'sına
   girmemiş kayıt auto_match hak etmiyor; en fazla `review`.

### G2 — Ayırt edicilik ölçüsü (IDF), `MIN_EXACT_SPAN`'in yerine **[önerilen ana iş]**

Sorun: span uzunluk ölçüyor, ayırt edicilik değil (B1). Çözüm: **elle stoplist
değil, indeksten türetilmiş doküman frekansı.** Build zamanında (`ingest/build.py`)
token → DF tablosu üret, artifact olarak yaz; gate `exact_match_text`'in
IDF toplamına / min-IDF'ine eşik koysun.

Bu, **P4'ün reddedilme gerekçesini doğrudan çözer.** P4 "%100 precision ama
sürekli büyüyen brittle domain-listesi ister, `decompose.py`'ın 'kural yazma,
veriye sor' felsefesine aykırı" diye reddedilmişti. DF tablosu tam olarak
"veriye sorma"nın kendisi: elle bakım yok, korpus değişince kendini günceller,
`_name_variants`/`aliases` ile aynı kaynaktan gelir.

Ölçülen taban: en sık tokenler `of` %14.4, `university` %9.4, `institute` %7.3,
`hospital` %5.1 — ayrım net, eşik bulmak kolay.

### G3 — Kapsama (coverage) sinyali: #6'yı `decompose` bağımlılığı olmadan kurtarır

DURUM §6d'de #6 tsr-auto şu yüzden çıkarıldı: güvenlik kilidi
`decompose.institution_part`'a dayanıyordu, o dağınık string'lerde bozuluyordu
("Calcutta ... Sciences" → kurum='Sciences').

**Coverage o bağımlılığı ortadan kaldırır**: parent exact span'i + subunit exact
span'i sorgunun hangi token aralıklarını kapsıyor, geriye ne kalıyor — bu doğrudan
`query_tokens` üzerinden ölçülür, `institution_part`'a hiç güvenmez. Açıklanmayan
token oranı yüksekse (adres, şehir, ülke artığı) auto verme. Reddedilen iki vaka
(locator "Calcutta" düşmesi, "Acıbadem/Adana" şehir çelişkisi) tam olarak
"açıklanmayan yüksek-IDF token" vakaları — G2 ile birlikte bloklanabilirler.

Ayrıca: parent ve subunit exact span'lerinin sorguda **çakışması** durumunda
(ikisi de aynı metni sahipleniyor) auto verme.

### G4 — Hipotez mutabakatı (bedava kanıt)

`decomposed.hypotheses[*].matched_parent_id` üzerinde oy: seçilen exact parent'ı
kaç hipotez destekliyor. Tam mutabakat → auto'yu güçlendir; hipotezler farklı
parent'lara dağılmışsa (özellikle `boundary_score` düşükken) auto'yu `review`'a
çek. `resolve`'a hiç dokunmaz, gate-lokal.

### G5 — Subunit'i parent-koşullu raporla (C1'in karşılığı)

`prefer_parent_id` daralması başarısız olduğunda `ambiguous` yerine `review` +
`signals` içinde "N aday / M farklı parent altında" ver. `ambiguous`'u parent
tarafına sakla — orada gerçekten nadir (%0.01) ve anlamlı.

### G6 — Ölçüm belkemiği (gerçekte önce bu yapılmalı)

*Revize 2026-07-29.*

1. `data/eval/benchmark_500_sample.csv`'yi `gate-batch`'ten geçir → kategori
   kırılımlı baseline + etiketleme kuyruğu. Set hazır; koşmak ~16 dk.
   ⚠️ Ham sorgular kişisel veri — **repoya commit edilmez**
   (`.gitignore: data/eval/*_sample.csv`); repoya toplu metrikler girer.
2. `tests/unit/test_gate.py`'a A2 (tsr alt-küme, "india" tuzağı) ve B1
   (jenerik span=2 exact) için birer **kırmızı** test ekle — düzeltmeden önce.
3. Gold: **id-eşleme engeli YOK** — v2/v3 ES id uzayları aynı; DURUM §6d'nin
   uyuşmazlık gözlemi `isimler_tekrarsız.csv`'nin `canonical_id` kolonuna ait
   (o kolon ES id'si değil), id uzayına değil. Gerçek engel gold'un kendisinin
   olmaması. Ara adım: yalnız **auto_match satırlarını** etiketle — hedef metrik
   `auto_precision` zaten sadece o kovadan ölçülür (500 sorguda ~250 satır).
   39 `no_match` satırı hazır geliyor.

---

## 4. Tekrar denenmemesi gerekenler (kanıtlı red)

- **#6 tsr-auto**, `institution_part` kilidiyle → G3 (coverage) olmadan tekrar
  denenmemeli.
- **P4 soft-exact**, elle domain stoplist ile → G2 (korpus DF) formunda yeniden
  ele alınmalı, eski formda değil.
- **bm25_norm / kosinüsün karara geri dönmesi** — gerekçe sağlam ve ölçülü.
- **Aşama-2 hakem, şema-fix** (§6 kararları).

---

## 5. Özet

Gate'in omurgası doğru ve savunulabilir. Asıl açıklar:

1. `token_set_ratio`'nun alt-küme davranışı `no_match` kapısını **öldürmüş**, review
   satırlarının sinyallerini ve confidence'ını **yanlış adaya** bağlamış (A2) —
   bm25 için doğru teşhis edilen hatanın tsr'de tekrarı.
2. exact'in **ayırt ediciliği** hiç ölçülmüyor; `MIN_EXACT_SPAN` uzunluk vekili
   olarak zayıf (B1). Çözüm elle liste değil, korpus DF (G2).
3. Elde olan kanıtın yarısı (hipotezler, alias, coverage, kapsama çakışması)
   **hiç okunmuyor** — hepsi gate-lokal, resolve'a dokunmadan kullanılabilir.
4. Subunit belirsizliği yapısal (%79 ad çakışması) ve bugünkü haliyle parent'ın
   belirsizliğini tekrarlıyor.
5. **Doğruluk hiç ölçülmedi.** `auto_precision_target: 0.98` bir hedef, bir ölçüm
   değil. G6 olmadan G1–G5 körlemesine yapılır.
