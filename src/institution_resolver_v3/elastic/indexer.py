"""Kanonik JSONL -> ES bulk index + force-merge (determinizm gun-1).

Akis: parent JSONL'i belleğe al (parent-adi indeksi icin) -> parent + subunit
belgelerini uret (document.build_document) -> bulk index -> force-merge 1 segment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from institution_resolver_v3.elastic.client import es_config, get_client
from institution_resolver_v3.elastic.document import build_document, build_parent_name_index
from institution_resolver_v3.elastic.mappings import build_index_body


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def create_index(client: Elasticsearch, index: str, *, recreate: bool = False) -> None:
    if recreate and client.indices.exists(index=index):
        client.indices.delete(index=index)
    if not client.indices.exists(index=index):
        client.indices.create(index=index, **build_index_body())


def _compute_embeddings(
    records: list[dict[str, Any]],
    parent_names: dict[str, str],
    cache_path: str | Path | None = None,
) -> list[list[float]]:
    """Tum kayitlar icin embed metni uret + encode et (MPS). Sira korunur.

    Disk cache: `cache_path` (npz) varsa ve id'ler AYNI sirayla eslesiyorsa
    yeniden encode etmez (23 dk'lik encode'u tekrarlamamak icin - ES bulk
    timeout'unda kaybolmasin).
    """
    import numpy as np

    from institution_resolver_v3.embedding.encoder import encode_texts
    from institution_resolver_v3.embedding.text_builder import build_embed_text

    ids = [r["id"] for r in records]
    if cache_path and Path(cache_path).exists():
        data = np.load(cache_path, allow_pickle=True)
        if list(data["ids"]) == ids:
            return data["vecs"].tolist()

    texts = [build_embed_text(r, parent_names) for r in records]
    vecs = encode_texts(texts)
    if cache_path:
        np.savez(cache_path, ids=np.array(ids, dtype=object), vecs=vecs)
    return [v.tolist() for v in vecs]


def _actions(
    parents: list[dict[str, Any]],
    subunits: list[dict[str, Any]],
    index: str,
    embeddings: list[list[float]] | None = None,
) -> Iterator[dict[str, Any]]:
    parent_names = build_parent_name_index(parents)
    records = parents + subunits
    for i, rec in enumerate(records):
        doc = build_document(rec, parent_names)
        if embeddings is not None:
            doc["embedding"] = embeddings[i]
        # KRITIK: parent ve subunit id uzaylari ORTUSUYOR (55.431 ortak id).
        # record_type oneki olmadan _id cakisir, kayitlar birbirini ezer.
        # Gercek id `_source.id`'de korunur (arama onu doner, _id'yi degil).
        yield {"_index": index, "_id": f"{rec['record_type']}:{rec['id']}", "_source": doc}


def index_data(
    parent_jsonl: str | Path,
    subunit_jsonl: str | Path,
    *,
    client: Elasticsearch | None = None,
    index: str | None = None,
    recreate: bool = True,
    chunk_size: int = 2000,
    with_embeddings: bool = False,
) -> dict[str, Any]:
    """JSONL'leri ES'e yukler. Doner: {indexed, errors, index}."""
    client = client or get_client()
    cfg = es_config()
    index = index or cfg["index"]

    parents = _read_jsonl(Path(parent_jsonl))
    subunits = _read_jsonl(Path(subunit_jsonl))

    create_index(client, index, recreate=recreate)

    embeddings = None
    if with_embeddings:
        parent_names = build_parent_name_index(parents)
        cache = Path(parent_jsonl).parent / "embeddings.npz"
        embeddings = _compute_embeddings(parents + subunits, parent_names, cache_path=cache)
        chunk_size = min(chunk_size, 500)   # vektorlu bulk agir -> kucuk chunk

    success, errors = bulk(
        client,
        _actions(parents, subunits, index, embeddings),
        chunk_size=chunk_size,
        raise_on_error=False,
        request_timeout=300,
    )
    client.indices.refresh(index=index)
    # determinizm gun-1: tek segment (buyuk vektor index'te yavas -> best-effort, uzun timeout)
    try:
        client.options(request_timeout=1200).indices.forcemerge(index=index, max_num_segments=1)
    except Exception as e:  # merge sunucuda devam edebilir; belgeler zaten yuklu
        print(f"[uyari] forcemerge timeout/hata (belgeler yuklu, merge arka planda surebilir): {e}")

    # alias baglama (institutions -> institutions_v1)
    alias = cfg.get("alias")
    if alias:
        client.indices.put_alias(index=index, name=alias)

    return {"indexed": success, "errors": errors, "index": index,
            "parents": len(parents), "subunits": len(subunits)}
