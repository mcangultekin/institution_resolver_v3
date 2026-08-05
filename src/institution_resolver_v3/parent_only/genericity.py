"""Ad ayirt-ediciligi: "bu ad katalogda kac BASKA kurumun adinin icinde geciyor".

NEDEN (olculdu 2026-08-05)
--------------------------
Gate'in karar omurgasi `exact_match` ve auto icin `MIN_EXACT_SPAN=2` sarti var -
ama bu, eslesmenin UZUNLUGUNU olcuyor, AYIRT EDICILIGINI degil. Sonuc: sorgu
"Gaziantep Sehitkamil State Hospital" derken katalogdaki jenerik `State Hospital`
kaydi span=2 exact aliyor ve `auto_match` cikiyor.

Uc bagimsiz analiz ayni koke isaret etti (bkz. docs / oturum notlari):
kanarya etkisi (11 satir), ulke celiskisi (11 satir), hakemin ambiguous'ta
gate'i duzelttigi 8 satir - hepsinde secilen ad jenerik bir parcaydi
(`State Hospital`, `Department of Health`, `University School`,
`Ministry of Science`, `University of Technology`).

Sinyalin kendisi parametresiz: adin katalogda kac baska kayit adinin ICINDE
ardisik parca olarak gectigi. Olculen ayrim keskin:

    gate'in YANLIS sectikleri        gate'in DOGRU sectikleri
      University of Technology 191     HACETTEPE ÜNİVERSİTESİ  0
      City Hospital             81     Ovidius University      0
      Department of Health      62     ANKARA ÜNİVERSİTESİ     1
      State Hospital            20     Georgetown University   1
      University School         16     Newcastle University    2

NEDEN ES, neden on-hesaplanmis tablo DEGIL
------------------------------------------
`match_phrase` (name.ascii) offline n-gram sayimiyla BIREBIR ayni sonucu veriyor
(8/8 dogrulandi: State Hospital 20, Department of Health 62, University of
Technology 191, ANKARA ÜNİVERSİTESİ 1 ...). ES'ten okumak (a) yeni bir artefakt
ve build adimi getirmiyor, (b) index yeniden olusturulunca sayilar kendiliginden
guncelleniyor - bayat kalamiyor.

Maliyet: sorgu basina TEK msearch round-trip (havuzdaki tum adaylar icin).
"""

from __future__ import annotations

from typing import Any, Callable

# (adlar) -> {ad: kac baska kayit adinin icinde geciyor}
CountFn = Callable[[list[str]], dict[str, int]]


def es_containment_counts(
    names: list[str], *, client: Any = None, index: str | None = None
) -> dict[str, int]:
    """Her ad icin "kac BASKA parent kaydinin adi bu adi iceriyor" sayisini doner.

    Adin KENDI kaydi dusulur (bu yuzden -1): benzersiz bir ad 0 alir, jenerik bir
    parca yuksek alir. Bir alt-sorgu hata verirse o ad sozlukte 0 olur - sinyal
    yoksa koruma calismaz, sorgu normal akisina devam eder (sessiz cokme yok,
    yalnizca ihtiyatli varsayilan).
    """
    uniq = [n for n in dict.fromkeys(names) if n and n.strip()]
    if not uniq:
        return {}

    from institution_resolver_v3.elastic.client import es_config, get_client

    client = client or get_client()
    index = index or es_config()["index"]

    body: list[dict[str, Any]] = []
    for name in uniq:
        body.append({"index": index})
        body.append(
            {
                "size": 0,
                "track_total_hits": True,
                "query": {
                    "bool": {
                        "filter": [{"term": {"record_type": "parent"}}],
                        "must": [{"match_phrase": {"name.ascii": name}}],
                    }
                },
            }
        )
    resp = client.msearch(body=body)

    out: dict[str, int] = {}
    for name, r in zip(uniq, resp["responses"]):
        if r.get("error") or "hits" not in r:
            out[name] = 0
            continue
        total = r["hits"]["total"]
        n = total["value"] if isinstance(total, dict) else int(total)
        out[name] = max(n - 1, 0)  # kendi kaydini dus
    return out
