"""Hakem prompt'u - F4 (bkz. docs/DURUM.md 2026-07-24 Pecs ornegi tasarim notlari).

HAM METIN ILKESI: hakeme tam orijinal sorgu + decompose'un hipotez sinirlari
(kurum kismi) verilir - ON-YAPILANDIRMA YOK. `unit_part` (virgul-segmentasyonu
dahil hicbir kural-tabanli bolme) hic gosterilmez: hangi kelimenin birim,
hangisinin konum/gurultu oldugu ayrimini LLM ham metinden KENDISI yapar
(kullanici itirazi 2026-07-24 - marker-bolme reddiyle ayni gerekce, bkz.
retrieve/decompose.py modul docstring'i "KARAR DEGIL HIPOTEZ").

Kosinus (ham deger) hakeme ARTIK GOSTERILMEZ (2026-07-27 olcumu): embedding
modeli multilingual-e5-base anizotropik - tum benzerlikler ~[0.74, 0.87] dar
bandina sikisiyor (alakasiz kayit, hatta "kuru fasulye tarifi" bile ~0.85 alir)
ve dogru esleme havuz-ici kosinus siralamasinda ort. 4. cikiyor (yalnizca 1/8
kez 1.). Yani ham/goreli kosinus hakem icin YANILTICI bir ranking sinyaliydi;
prompt'tan kaldirildi. kNN retrieval'da KALIR - cosinus'un asil, kanitlanmis
degeri orada (capraz-dilli recall: bm25'in kacirdigi adayi havuza sokar).

`reasoning` alani KALDIRILDI (2026-07-24, kullanici karari - hiz): sadece
verdict+matched_id isteniyor, aciklama YOK. LLM'in uretmesi gereken token
sayisi ~200'den ~10-20'ye dustu, uretim suresi de orantili azaldi (bkz.
docs/DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md).
"""

from __future__ import annotations

from institution_resolver_v3.judge.candidates import CandidateView
from institution_resolver_v3.retrieve.decompose import DecomposedQuery

_SCHEMA_EXAMPLE = """{
  "parent": {"verdict": "auto_match|review|ambiguous|no_match", "matched_id": "<id|ad>" | null},
  "unit_phrase": "<sorgudaki EN SPESİFİK birim ifadesi, sorgudan AYNEN kopyala>" | null,
  "subunit": {"verdict": "auto_match|review|ambiguous|no_match", "matched_id": "<id|ad>" | null} | null
}"""


def _fmt_exact(c: CandidateView) -> str:
    if not c.exact_match:
        return "tam_eşleşme=hayır"
    part = f' (sorgudaki eşleşen parça: "{c.exact_match_text}")' if c.exact_match_text else ""
    return f"tam_eşleşme=EVET{part}"


def _fmt_alias(c: CandidateView) -> str:
    return f'  diğer_adı="{c.best_alias}"' if c.best_alias else ""


def _fmt_parent(c: CandidateView) -> str:
    loc = f"ülke={c.country or '?'} şehir={c.city or '?'}"
    return (
        f"  id={c.id}  ad=\"{c.name}\"{_fmt_alias(c)}  {loc}\n"
        f"    bm25={c.bm25_norm:.3f}  "
        f"token_benzerlik={c.token_set_ratio:.1f}  nitelik_çelişkisi={'evet' if c.qualifier_conflict else 'hayır'}"
        f"  {_fmt_exact(c)}"
    )


def _fmt_subunit(c: CandidateView) -> str:
    flag = " [kurum-filtresinden geçti]" if c.passed_parent_filter else ""
    loc = f"ülke={c.country or '?'} şehir={c.city or '?'}"
    return (
        f"  id={c.id}  ad=\"{c.name}\"{_fmt_alias(c)}  bağlı_kurum=\"{c.parent_name or '?'}\"  "
        f"tür=\"{c.kind_label or '?'}\"  {loc}{flag}\n"
        f"    bm25={c.bm25_norm:.3f}  "
        f"token_benzerlik={c.token_set_ratio:.1f}  nitelik_çelişkisi={'evet' if c.qualifier_conflict else 'hayır'}"
        f"  {_fmt_exact(c)}"
    )


def build_prompt(
    query: str,
    decomposed: DecomposedQuery,
    parents: list[CandidateView],
    subunits: list[CandidateView],
) -> str:
    hyp_lines = "\n".join(
        f"  H{i}: kurum-kısmı=\"{h.institution_part}\"  (bu hipotezi öneren aday: "
        f"{h.matched_parent_name or '—'}, güven={h.boundary_score:.1f})"
        for i, h in enumerate(decomposed.hypotheses or [])
    ) or "  (hipotez üretilemedi)"

    parent_lines = "\n".join(_fmt_parent(c) for c in parents) or "  (aday yok)"
    subunit_lines = "\n".join(_fmt_subunit(c) for c in subunits) or "  (aday yok)"

    # SABIT blok basta, DEGISKEN veri (sorgu+hipotez+adaylar) sonda (2026-07-27,
    # Asama 1 hiz paketi): Ollama ayni prefix'in KV-cache'ini yeniden kullanir -
    # sorgu 3. satirdayken cache her cagrida 2. satirda kiriliyordu ve ~1.5k
    # token'lik talimat blogu her seferinde yeniden isleniyordu.
    return f"""Görev: serbest metin bir kurum ifadesini KATALOG'daki doğru kayıtla eşleştir.
Katalog iki seviyeli: KURUM (üniversite/ana kuruluş) + ona bağlı ALT-BİRİM (fakülte/bölüm/enstitü vb.).
Aşağıda önce kurallar, sonra SORGU ve aday listeleri gelir.

HİPOTEZ NOTU: sorguyla birlikte verilecek "sınır hipotezleri" KESİN DEĞİLDİR -
arama sisteminin ürettiği olası kurum-adı aralıklarıdır; birden fazlası doğru
olabilir, hiçbiri de tam isabet olmayabilir. Bir ÖN-AYRIŞTIRMA değildir, sadece
ipucudur. Sorgunun neresinin kurum, neresinin alt-birim (bölüm/fakülte/enstitü/
konum vb. karışık "artık" metin) olduğuna SEN, ham sorgu metninin tamamına
bakarak karar ver. Virgülle ayrılmış parçalar da otomatik olarak "birim" ya da
"konum/gürültü" sayılmamalı - kirli veride bu ayrım sabit bir kuralla
yapılamıyor, senin muhakemen gerekiyor.

TAM_EŞLEŞME NOTU: "tam_eşleşme=EVET", bu adayın adının (ya da bilinen bir
alias'ının) sorgunun İÇİNDE kesintisiz bir parça olarak geçtiği anlamına gelir -
sorgunun TAMAMIYLA aynı olduğu anlamına GELMEZ. Uzun, çok parçalı bir sorguda
birden fazla aday tam_eşleşme alabilir (her biri sorgunun FARKLI bir parçasına
denk düşer). Her EVET'in yanında sorgunun hangi parçasıyla eşleştiği ("eşleşen
parça") gösterilir. Bu yüzden tam_eşleşme, "bu aday sorgudaki O parçanın doğru
karşılığı" için güçlü kanıttır ama "bu aday sorgunun İSTENEN seviyedeki cevabı"
demek DEĞİLDİR: sorgudaki EN SPESİFİK birim ifadesi, adayın eşleşen parçasının
DIŞINDA kalıyorsa (ör. eşleşen parça "bölüm"ken sorguda ayrıca onun altındaki
"bilim dalı" da geçiyorsa), tam_eşleşme'si olmayan ama o en spesifik parçaya
karşılık gelen aday tercih edilmelidir.

KARAR KURALLARI:
- Kurum (parent) ve alt-birim (subunit) kararını AYRI ayrı ver - biri diğerini
  otomatik belirlemez.
- İki liste AYRIDIR: parent.matched_id SADECE "KURUM ADAYLARI" listesinden,
  subunit.matched_id SADECE "ALT-BİRİM ADAYLARI" listesinden seçilebilir -
  listeler arası id kullanmak GEÇERSİZDİR.
- Sorgu ÜÇ seviyeli olabilir (ör. Üniversite > Fakülte > Bölüm). Katalog ise
  İKİ seviyeli. Bu durumda: parent = en üstteki ana kurum (üniversite),
  subunit = sorgudaki EN SPESİFİK birim (bölüm/bilim dalı). Aradaki seviye
  (fakülte) kendi başına eşleştirilecek bir hedef DEĞİLDİR - onu ne parent'a
  ne de subunit'e zorla; sadece bağlam ipucu olarak kullan.
- auto_match için adayın adı ya da diğer_adı, sorgudaki kurum adıyla GERÇEKTEN
  örtüşmeli. Sorgudaki kurum katalogda OLMAYABİLİR - hiçbir aday örtüşmüyorsa
  "en benzerini" SEÇME, no_match de. Alakasız bir kayda auto_match vermek, hiç
  cevap verememekten ÇOK daha pahalı bir hatadır.
- Ülke/şehir tutarlılığı ZORUNLU kontroldür: sorguda geçen ülke/şehir adayın
  ülke/şehriyle çelişiyorsa (ör. sorguda "Uzbekistan"/"Muğla" geçerken aday
  RU/Moscow ya da US ise) o adaya auto_match VERME - aynı adlı ama başka
  ülkedeki kurum YANLIŞ kurumdur; no_match ya da review kullan.
- "parent=auto_match + subunit=no_match" GEÇERLİ ve YAYGIN bir sonuçtur: kurum
  bulunur ama sorgudaki birim ifadesinin katalogda karşılığı yoksa, sadece
  subunit'i no_match yap; bu, parent kararını DÜŞÜRMEZ.
- Sorguda hiç alt-birim ifadesi YOKSA (yalnızca kurum adı soruluyorsa),
  "subunit" alanını TAMAMEN "null" yap - bunu "no_match" ile KARIŞTIRMA
  ("no_match" = birim ifadesi var ama katalogda karşılığı bulunamadı).
- verdict değerleri: "auto_match" (yüksek güven, tek net aday), "review"
  (doğru görünüyor ama insan onayı önerilir), "ambiguous" (birden fazla makul
  aday var, ayırt edilemiyor), "no_match" (hiçbir aday uymuyor / katalogda yok).
- matched_id, seçtiğin adayın id'si ve adı "id|ad" biçiminde birleştirilerek
  yazılmalı (ör. "S3|GERİATRİ BİLİM DALI") - SADECE aday listelerinde yer alan
  adaylardan biri olmalı, yeni id/ad UYDURMA. "no_match" durumunda matched_id
  "null" olmalı.

- "unit_phrase": subunit kararını vermeden ÖNCE, sorgudaki EN SPESİFİK birim
  ifadesini (en alt seviye - ör. bilim dalı > bölüm > fakülte sıralamasında en
  alttaki) sorgudan AYNEN kopyala. subunit.matched_id, bu ifadeye karşılık
  gelen adayı göstermeli. Sorguda hiç birim ifadesi yoksa null yap.

ÇIKTI: SADECE aşağıdaki şemaya uyan, başka HİÇBİR metin/açıklama/gerekçe
içermeyen KISA bir JSON döndür (gerekçe YAZMA, sadece verdict+matched_id):
{_SCHEMA_EXAMPLE}

SORGU (ham, orijinal, değiştirilmedi): "{query}"

Sınır hipotezleri (bkz. HİPOTEZ NOTU):
{hyp_lines}

KURUM ADAYLARI (parent):
{parent_lines}

ALT-BİRİM ADAYLARI (subunit):
{subunit_lines}

Şimdi kararını yukarıdaki kurallara ve şemaya uygun JSON olarak ver.
"""
