"""FastAPI dependency fonksiyonlari - app.state'ten kaynak okur + katman
fonksiyonlarini (resolve/gate/judge/decide) enjekte edilebilir kilar.

`get_*_fn` dependency'leri testlerde `app.dependency_overrides` ile sahte
(ES/Ollama'siz) fonksiyonlarla degistirilir - ayni ilke `eval/batch.py` vb.
modullerdeki `resolve_fn`/`judge_fn` parametreleriyle (bkz. tests/unit/test_batch.py)."""

from __future__ import annotations

from typing import Callable

from fastapi import Request

from institution_resolver_v3.api.jobs import JobManager
from institution_resolver_v3.decide.decide import decide as _decide
from institution_resolver_v3.gate.gate import gate as _gate
from institution_resolver_v3.judge.client import LlmClient
from institution_resolver_v3.judge.judge import judge as _judge
from institution_resolver_v3.retrieve.resolve import resolve as _resolve


def get_ollama_client(request: Request) -> LlmClient:
    return request.app.state.ollama_client


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_resolve_fn() -> Callable:
    return _resolve


def get_gate_fn() -> Callable:
    return _gate


def get_judge_fn() -> Callable:
    return _judge


def get_decide_fn() -> Callable:
    return _decide
