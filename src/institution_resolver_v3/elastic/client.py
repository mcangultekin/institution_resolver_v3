"""ES baglantisi (config'ten host/index)."""

from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from institution_resolver_v3.config import load_config


def get_client(host: str | None = None, request_timeout: int = 300) -> Elasticsearch:
    cfg = load_config()
    return Elasticsearch(host or cfg["elasticsearch"]["host"], request_timeout=request_timeout)


def es_config() -> dict[str, Any]:
    return load_config()["elasticsearch"]
