"""ES baglantisi (config'ten host/index)."""

from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from institution_resolver_v3.config import load_config


def get_client(host: str | None = None) -> Elasticsearch:
    cfg = load_config()
    return Elasticsearch(host or cfg["elasticsearch"]["host"], request_timeout=60)


def es_config() -> dict[str, Any]:
    return load_config()["elasticsearch"]
