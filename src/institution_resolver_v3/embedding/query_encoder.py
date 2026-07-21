"""Sorgu tarafi tekil kodlama - e5 "query: " oneki (belge "passage:"ten farkli).

Sorgu metni expand_query_text ile hazirlanir (kisaltma genisletme + gorunmez
karakter; case/aksan KORUNUR - belge tarafiyla simetrik dogal metin).
"""

from __future__ import annotations

import numpy as np

from institution_resolver_v3.config import load_config
from institution_resolver_v3.embedding.encoder import get_model
from institution_resolver_v3.normalize.query_pipeline import expand_query_text


def encode_query(text: str) -> np.ndarray:
    prefix = load_config()["embedding"]["query_prefix"]
    model = get_model()
    prepared = prefix + expand_query_text(text)
    vec = model.encode([prepared], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0]
