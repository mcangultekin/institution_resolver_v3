"""multilingual-e5-base kodlama (belge tarafi). MPS (Apple GPU) + cosine-normalize.

Vektorler normalize edilir (unit) -> ES dense_vector cosine ile uyumlu.
Model bir kez yuklenir (modul-duzeyi cache).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from institution_resolver_v3.config import load_config

_model: Any = None


def _emb_cfg() -> dict[str, Any]:
    return load_config()["embedding"]


def get_model(name: str | None = None, device: str | None = None) -> Any:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        cfg = _emb_cfg()
        _model = SentenceTransformer(name or cfg["model"], device=device or _pick_device())
    return _model


def _pick_device() -> str:
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def encode_texts(
    texts: list[str],
    *,
    batch_size: int | None = None,
    show_progress: bool = True,
) -> np.ndarray:
    """Metin listesini (dim,) normalize vektorlere kodlar. Shape: (n, dim)."""
    cfg = _emb_cfg()
    model = get_model()
    return model.encode(
        texts,
        batch_size=batch_size or cfg.get("batch_size", 64),
        normalize_embeddings=True,          # cosine icin unit vektor
        convert_to_numpy=True,
        show_progress_bar=show_progress,
    )
