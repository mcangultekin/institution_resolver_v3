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


def _actions(
    parents: list[dict[str, Any]],
    subunits: list[dict[str, Any]],
    index: str,
) -> Iterator[dict[str, Any]]:
    parent_names = build_parent_name_index(parents)
    for rec in parents:
        yield {"_index": index, "_id": rec["id"], "_source": build_document(rec, parent_names)}
    for rec in subunits:
        yield {"_index": index, "_id": rec["id"], "_source": build_document(rec, parent_names)}


def index_data(
    parent_jsonl: str | Path,
    subunit_jsonl: str | Path,
    *,
    client: Elasticsearch | None = None,
    index: str | None = None,
    recreate: bool = True,
    chunk_size: int = 2000,
) -> dict[str, Any]:
    """JSONL'leri ES'e yukler. Doner: {indexed, errors, index}."""
    client = client or get_client()
    cfg = es_config()
    index = index or cfg["index"]

    parents = _read_jsonl(Path(parent_jsonl))
    subunits = _read_jsonl(Path(subunit_jsonl))

    create_index(client, index, recreate=recreate)

    success, errors = bulk(
        client,
        _actions(parents, subunits, index),
        chunk_size=chunk_size,
        raise_on_error=False,
    )
    client.indices.refresh(index=index)
    # determinizm gun-1: tek segment
    client.indices.forcemerge(index=index, max_num_segments=1)

    # alias baglama (institutions -> institutions_v1)
    alias = cfg.get("alias")
    if alias:
        client.indices.put_alias(index=index, name=alias)

    return {"indexed": success, "errors": errors, "index": index,
            "parents": len(parents), "subunits": len(subunits)}
