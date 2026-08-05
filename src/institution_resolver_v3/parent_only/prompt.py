"""Parent-only hakem prompt'u.

Cekirdek `judge/prompt.py`nin kirpilmis hali DEGIL - kendi amacina gore yazildi.
Korunan ilkeler (hepsi canli bulgulardan, bkz. judge/prompt.py docstring'i):
- HAM METIN: tam orijinal sorgu + sinir hipotezleri verilir, on-yapilandirma yok.
- SABIT blok basta, DEGISKEN veri (sorgu + adaylar) sonda: Ollama ayni prefix'in
  KV-cache'ini yeniden kullanabilsin diye.
- Kosinus GOSTERILMEZ (2026-07-27: e5-base anizotropik, ~[0.74,0.87] dar bandinda
  yaniltici bir ranking sinyaliydi).
- Gerekce/aciklama ISTENMEZ: sadece verdict + matched_id.

Parent-only'ye OZGU iki kural eklendi:
1. Sorgudaki fakulte/bolum/enstitu ifadeleri HEDEF DEGIL, yalniz baglam ipucu.
2. Ama adayin KENDISI bilesik bir ad tasiyabilir ("İSTANBUL ÜNİVERSİTESİ-CERRAHPAŞA",
   "Ege Üniversitesi Tıp Fakültesi Hastanesi") - bunlar katalogda AYRI kurum
   kayitlaridir, alt-birim degil. Olculdu (500 sorgu): bu ikilem %1.6'da olusuyor.

Olcum: 8184 -> 2384 karakter (%71 kucuk), canli E4B'de ~62 s -> ~18 s / cagri.
"""

from __future__ import annotations

from institution_resolver_v3.judge.candidates import CandidateView
from institution_resolver_v3.retrieve.decompose import DecomposedQuery

_SCHEMA_EXAMPLE = """{"parent": {"verdict": "auto_match|review|ambiguous|no_match", "matched_id": "<id|ad>" | null}}"""


def _fmt_exact(c: CandidateView) -> str:
    if not c.exact_match:
        return "tam_eşleşme=hayır"
    part = f' (sorgudaki eşleşen parça: "{c.exact_match_text}")' if c.exact_match_text else ""
    return f"tam_eşleşme=EVET{part}"


def _fmt_genericity(count: int | None) -> str:
    """Adin ayirt ediciligi (bkz. genericity.py). Olculdu (26 sorgu, 3 varyant):
    bu satir eklenince hakem, jenerik kayda yanlis auto veren 11 vakanin 4'u
    yerine 7'sini duzeltti ve 15 saglam karardan hicbirini bozmadi. Bedeli
    ~%6 prompt token.

    Alternatif olarak denenen "token_benzerliğin önemi azdır" notu REDDEDILDI:
    ayni testte supheli vakalarda hicbir kazanc saglamadi (4/11) ve 15 saglam
    kararin 3'unu BOZDU - kucuk modele "su sinyale az guven" demek, yerine bilgi
    koymadan dogru calisan bir gostergeden uzaklastiriyor."""
    # Ifade, olculen varyantla BIREBIR ayni tutuluyor - 7/11 sonucu bu sozcuklerle
    # alindi ve kucuk modeller ifade degisikligine duyarli.
    if count is None:
        return ""
    if count <= 0:
        return "  (bu ad başka hiçbir kurumun adının içinde geçmiyor)"
    return f"  (bu ad katalogda {count} başka kurumun adının içinde geçiyor)"


def _fmt_parent(c: CandidateView, count: int | None = None) -> str:
    alias = f'  diğer_adı="{c.best_alias}"' if c.best_alias else ""
    return (
        f'  id={c.id}  ad="{c.name}"{alias}  ülke={c.country or "?"} şehir={c.city or "?"}\n'
        f"    token_benzerlik={c.token_set_ratio:.1f}  "
        f"nitelik_çelişkisi={'evet' if c.qualifier_conflict else 'hayır'}  {_fmt_exact(c)}"
        f"{_fmt_genericity(count)}"
    )


def build_parent_prompt(
    query: str,
    decomposed: DecomposedQuery,
    parents: list[CandidateView],
    name_counts: dict[str, int] | None = None,
) -> str:
    hyp_lines = "\n".join(
        f'  H{i}: kurum-kısmı="{h.institution_part}"  (öneren aday: '
        f"{h.matched_parent_name or '—'}, güven={h.boundary_score:.1f})"
        for i, h in enumerate(decomposed.hypotheses or [])
    ) or "  (hipotez üretilemedi)"
    nc = name_counts or {}
    parent_lines = "\n".join(
        _fmt_parent(c, nc.get(c.name) if name_counts else None) for c in parents
    ) or "  (aday yok)"

    return f"""Görev: serbest metin bir ifadeden KURUM'u (ana kuruluş) bul ve KATALOG'daki doğru kayıtla eşleştir.

Sorgu kirli ve serbest metindir: kurum adının yanında fakülte/bölüm/enstitü/
anabilim dalı gibi birim ifadeleri, şehir/ülke adları, kişi adları, unvanlar ve
başka gürültü bulunabilir. Bunlar SADECE bağlam ipucudur - eşleştirilecek hedef
DEĞİLDİR. Cevap her zaman ana kuruluştur (üniversite/hastane/bakanlık/şirket/enstitü).

DİKKAT - bileşik adlar: adayın KENDİSİ birim gibi görünen bir ad taşıyabilir
(ör. "İSTANBUL ÜNİVERSİTESİ-CERRAHPAŞA", "Ege Üniversitesi Tıp Fakültesi Hastanesi",
"Ministry of Agriculture and Forestry"). Bunlar katalogda KENDİ BAŞINA birer kurum
kaydıdır, alt-birim değil. Yani "adında fakülte/hastane geçiyor" diye bir adayı
eleme; sorguya gerçekten hangisi karşılık geliyorsa onu seç. Hem şemsiye kurum hem
bileşik kayıt listede varsa ve hangisinin kastedildiği ayırt edilemiyorsa "ambiguous" de.

HİPOTEZ NOTU: aşağıdaki "sınır hipotezleri" KESİN DEĞİLDİR - arama sisteminin
ürettiği olası kurum-adı aralıklarıdır; birden fazlası doğru olabilir, hiçbiri de
isabet etmeyebilir. Bir ön-ayrıştırma değil, sadece ipucudur. Sorgunun neresinin
kurum adı olduğuna SEN, ham metnin tamamına bakarak karar ver.

TAM_EŞLEŞME NOTU: "tam_eşleşme=EVET", adayın adının (ya da bilinen bir alias'ının)
sorgunun İÇİNDE kesintisiz bir parça olarak geçtiği anlamına gelir - sorgunun
TAMAMIYLA aynı olduğu anlamına GELMEZ. Uzun sorgularda birden fazla aday
tam_eşleşme alabilir (her biri sorgunun farklı bir parçasına denk düşer); her
EVET'in yanında hangi parçayla eşleştiği gösterilir.

KARAR KURALLARI:
- auto_match için adayın adı ya da diğer_adı, sorgudaki kurum adıyla GERÇEKTEN
  örtüşmeli. Sorgudaki kurum katalogda OLMAYABİLİR - hiçbir aday örtüşmüyorsa
  "en benzerini" SEÇME, no_match de. Alakasız bir kayda auto_match vermek, hiç
  cevap verememekten ÇOK daha pahalı bir hatadır.
- Ülke/şehir tutarlılığı ZORUNLU kontroldür: sorguda geçen ülke/şehir adayınkiyle
  çelişiyorsa (ör. sorguda "Muğla" geçerken aday US/Moscow ise) auto_match VERME -
  aynı adlı ama başka ülkedeki kurum YANLIŞ kurumdur; no_match ya da review kullan.
- verdict değerleri: "auto_match" (yüksek güven, tek net aday), "review" (doğru
  görünüyor ama insan onayı önerilir), "ambiguous" (birden fazla makul aday,
  ayırt edilemiyor), "no_match" (hiçbir aday uymuyor / katalogda yok).
- matched_id, seçtiğin adayın id'si ve adı "id|ad" biçiminde birleştirilerek
  yazılmalı (ör. "P2|EGE ÜNİVERSİTESİ") - SADECE aşağıdaki listede yer alan
  adaylardan biri olmalı, yeni id/ad UYDURMA. "no_match" durumunda matched_id null.

ÇIKTI: SADECE aşağıdaki şemaya uyan, başka HİÇBİR metin/açıklama/gerekçe
içermeyen KISA bir JSON döndür (gerekçe YAZMA):
{_SCHEMA_EXAMPLE}

SORGU (ham, orijinal, değiştirilmedi): "{query}"

Sınır hipotezleri (bkz. HİPOTEZ NOTU):
{hyp_lines}

KURUM ADAYLARI:
{parent_lines}

Şimdi kararını yukarıdaki kurallara ve şemaya uygun JSON olarak ver.
"""
