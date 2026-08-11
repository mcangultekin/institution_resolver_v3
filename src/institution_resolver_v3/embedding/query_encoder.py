"""Sorgu tarafi tekil kodlama - e5 "query: " oneki (belge "passage:"ten farkli).

Sorgu metni expand_query_text ile hazirlanir (kisaltma genisletme + gorunmez
karakter; case/aksan KORUNUR - belge tarafiyla simetrik dogal metin).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from institution_resolver_v3.config import load_config
from institution_resolver_v3.embedding.encoder import get_model
from institution_resolver_v3.normalize.query_pipeline import expand_query_text

# prewarm() ile TOPLU kodlanmis vektorlerin gecici tamponu (bkz. prewarm docstring).
# VARSAYILAN AKISTA HEP BOSTUR - kimse prewarm cagirmazsa _encode_prepared aynen
# eskisi gibi tek tek kodlar, vektorler byte-denk kalir.
_prewarmed: dict[str, np.ndarray] = {}


@lru_cache(maxsize=2048)
def _encode_prepared(prepared: str) -> np.ndarray:
    """Hazirlanmis metni (prefix + expand uygulanmis) kodlar - DETERMINISTIK,
    o yuzden cache'lenir. Bir resolve() icinde ayni metin (sorgunun kendisi,
    "Üniversitesi" gibi jenerik parcalar) BM25/kNN + cosine_fn yollarindan
    defalarca kodlaniyordu; cache tekrar transformer gecisini eler.

    Donen dizi READ-ONLY isaretlenir: cache'lenmis vektor paylasilir, bir
    tuketici yerinde degistirirse (vec[:] = ...) cache zehirlenirdi - mevcut
    cagiranlar (.tolist() / np.asarray kopyasi) degistirmiyor ama bayrak bunu
    kalicilastirir.
    """
    vec = _prewarmed.pop(prepared, None)
    if vec is None:
        model = get_model()
        vec = model.encode([prepared], normalize_embeddings=True, convert_to_numpy=True)[0]
    vec.flags.writeable = False
    return vec


def _prepare(text: str) -> str:
    prefix = load_config()["embedding"]["query_prefix"]
    return prefix + expand_query_text(text)


def prewarm(texts: list[str]) -> int:
    """Verilen sorgu metinlerini TEK batch'te kodlayip tampona koyar; sonraki
    `encode_query` cagrilari transformer'a hic gitmez.

    Neden: bir resolve() icinde ~3,5 AYRI metin kodlaniyor (tam sorgu + decompose'un
    sectigi hipotez parcalari) ve her biri ayri bir `model.encode([tek])` geciyor.
    Olculen (M4, 2026-08-11): batch=1 icin 18,9 ms/metin, batch>=8 icin 5,2 ms/metin.

    UYARI - byte-denk DEGIL: batch'te kodlanan vektor tek tek kodlanandan
    ~3e-07 sapar (kosinus 0,9999998). Gate esiklerle calistigi icin teorik olarak
    bir karari cevirebilir. Bu yuzden VARSAYILAN AKIS BUNU CAGIRMAZ; yalnizca
    envanter modu (jobs/inventory.py) acikca devreye alir.

    Tampon her cagride sifirlanir: bir onceki sorgudan artan (kullanilmayan)
    vektorler birikmez. Donen deger: gercekten kodlanan metin sayisi.
    """
    _prewarmed.clear()
    prepared = list(dict.fromkeys(_prepare(t) for t in texts if t and t.strip()))
    if len(prepared) < 2:  # tek metinde batch'in anlami yok - eski yol daha ucuz
        return 0
    model = get_model()
    cfg = load_config()["embedding"]
    vecs = model.encode(
        prepared,
        batch_size=min(len(prepared), cfg.get("batch_size", 32)),
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    for key, vec in zip(prepared, vecs):
        _prewarmed[key] = vec
    return len(prepared)


def encode_query(text: str) -> np.ndarray:
    return _encode_prepared(_prepare(text))
