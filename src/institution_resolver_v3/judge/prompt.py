"""Hakem prompt'u - F4 (bkz. docs/DURUM.md 2026-07-24 Pecs ornegi tasarim notlari).

HAM METIN ILKESI: hakeme tam orijinal sorgu + decompose'un hipotez sinirlari
(kurum kismi) verilir - ON-YAPILANDIRMA YOK. `unit_part` (virgul-segmentasyonu
dahil hicbir kural-tabanli bolme) hic gosterilmez: hangi kelimenin birim,
hangisinin konum/gurultu oldugu ayrimini LLM ham metinden KENDISI yapar
(kullanici itirazi 2026-07-24 - marker-bolme reddiyle ayni gerekce, bkz.
retrieve/decompose.py modul docstring'i "KARAR DEGIL HIPOTEZ").

Kosinus bandi dar oldugu icin (alakasizlar bile +0.75-0.85 alabiliyor,
docs/DURUM.md) prompt ACIKCA "mutlak esik yok" uyarisi tasir.

`reasoning` alani KALDIRILDI (2026-07-24, kullanici karari - hiz): sadece
verdict+matched_id isteniyor, aciklama YOK. LLM'in uretmesi gereken token
sayisi ~200'den ~10-20'ye dustu, uretim suresi de orantili azaldi (bkz.
docs/DENEY_2026-07-24_gemma_e2b_e4b_karsilastirma.md).
"""

from __future__ import annotations

from institution_resolver_v3.judge.candidates import CandidateView
from institution_resolver_v3.retrieve.decompose import DecomposedQuery

_SCHEMA_EXAMPLE = """{
  "query": "<orijinal sorgu, degistirmeden>",
  "parent": {"verdict": "auto_match|review|ambiguous|no_match", "matched_id": "<id>" | null},
  "subunit": {"verdict": "auto_match|review|ambiguous|no_match", "matched_id": "<id>" | null} | null
}"""


def _fmt_cosine(v: float | None) -> str:
    return f"{v:+.3f}" if v is not None else "yok"


def _fmt_parent(c: CandidateView) -> str:
    loc = f"ülke={c.country or '?'} şehir={c.city or '?'}"
    return (
        f"  id={c.id}  ad=\"{c.name}\"  {loc}\n"
        f"    bm25={c.bm25_norm:.3f}  kosinüs={_fmt_cosine(c.cosine)}  "
        f"token_benzerlik={c.token_set_ratio:.1f}  nitelik_çelişkisi={'evet' if c.qualifier_conflict else 'hayır'}"
        f"  tam_eşleşme={'EVET' if c.exact_match else 'hayır'}"
    )


def _fmt_subunit(c: CandidateView) -> str:
    flag = " [kurum-filtresinden geçti]" if c.passed_parent_filter else ""
    loc = f"ülke={c.country or '?'} şehir={c.city or '?'}"
    return (
        f"  id={c.id}  ad=\"{c.name}\"  bağlı_kurum=\"{c.parent_name or '?'}\"  "
        f"tür=\"{c.kind_label or '?'}\"  {loc}{flag}\n"
        f"    bm25={c.bm25_norm:.3f}  kosinüs={_fmt_cosine(c.cosine)}  "
        f"token_benzerlik={c.token_set_ratio:.1f}  nitelik_çelişkisi={'evet' if c.qualifier_conflict else 'hayır'}"
        f"  tam_eşleşme={'EVET' if c.exact_match else 'hayır'}"
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

    return f"""Görev: serbest metin bir kurum ifadesini KATALOG'daki doğru kayıtla eşleştir.
Katalog iki seviyeli: KURUM (üniversite/ana kuruluş) + ona bağlı ALT-BİRİM (fakülte/bölüm/enstitü vb.).

SORGU (ham, orijinal, değiştirilmedi): "{query}"

Sınır hipotezleri (KESİN DEĞİL - arama sisteminin ürettiği olası kurum-adı
aralıkları, birden fazlası doğru olabilir, hiçbiri de tam isabet olmayabilir):
{hyp_lines}

ÖNEMLİ: Yukarıdaki hipotezler bir ÖN-AYRIŞTIRMA değildir, sadece ipucudur.
Sorgunun neresinin kurum, neresinin alt-birim (bölüm/fakülte/enstitü/konum vb.
karışık "artık" metin) olduğuna SEN, ham sorgu metninin tamamına bakarak karar
ver. Virgülle ayrılmış parçalar da otomatik olarak "birim" ya da "konum/gürültü"
sayılmamalı - kirli veride bu ayrım sabit bir kuralla yapılamıyor, senin
muhakemen gerekiyor.

KURUM ADAYLARI (parent):
{parent_lines}

ALT-BİRİM ADAYLARI (subunit):
{subunit_lines}

TAM_EŞLEŞME NOTU: "tam_eşleşme=EVET", sorgunun (normalize edilmiş hali) bu
adayın adıyla ya da bilinen bir yazım/alias'ıyla BİREBİR aynı olduğu anlamına
gelir - token_benzerlik=100'den DAHA GÜÇLÜ bir kanıttır (o fazla/az kelimeye
tolerans gösterir, tam_eşleşme göstermez). Ama tek başına "doğru SEVİYEDE"
olduğu anlamına gelmez - ör. sorguda bölüm isteniyorsa ve tam_eşleşme veren
aday aslında bir FAKÜLTEyse, bu hâlâ yanlış seviyede bir cevap olabilir.

KOSİNÜS UYARISI: Kosinüs bandı dar - alakasız adaylar bile +0.75/+0.85 gibi
yüksek değerler alabiliyor. MUTLAK bir eşik YOK; adaylar ARASI GÖRELİ farka ve
diğer sinyallerle (bm25, token_benzerlik, nitelik_çelişkisi, ülke/şehir
tutarlılığı) BİRLİKTE oku.

KARAR KURALLARI:
- Kurum (parent) ve alt-birim (subunit) kararını AYRI ayrı ver - biri diğerini
  otomatik belirlemez.
- "parent=auto_match + subunit=no_match" GEÇERLİ ve YAYGIN bir sonuçtur: kurum
  bulunur ama sorgudaki birim ifadesinin katalogda karşılığı yoksa, sadece
  subunit'i no_match yap; bu, parent kararını DÜŞÜRMEZ.
- Sorguda hiç alt-birim ifadesi YOKSA (yalnızca kurum adı soruluyorsa),
  "subunit" alanını TAMAMEN "null" yap - bunu "no_match" ile KARIŞTIRMA
  ("no_match" = birim ifadesi var ama katalogda karşılığı bulunamadı).
- verdict değerleri: "auto_match" (yüksek güven, tek net aday), "review"
  (doğru görünüyor ama insan onayı önerilir), "ambiguous" (birden fazla makul
  aday var, ayırt edilemiyor), "no_match" (hiçbir aday uymuyor / katalogda yok).
- matched_id SADECE yukarıda listelenen id'lerden biri olmalı - yeni id UYDURMA.
  "no_match" durumunda matched_id "null" olmalı.

ÇIKTI: SADECE aşağıdaki şemaya uyan, başka HİÇBİR metin/açıklama/gerekçe
içermeyen KISA bir JSON döndür (gerekçe YAZMA, sadece verdict+matched_id):
{_SCHEMA_EXAMPLE}
"""
