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
    model = get_model()
    vec = model.encode([prepared], normalize_embeddings=True, convert_to_numpy=True)[0]
    vec.flags.writeable = False
    return vec


def encode_query(text: str) -> np.ndarray:
    prefix = load_config()["embedding"]["query_prefix"]
    return _encode_prepared(prefix + expand_query_text(text))
