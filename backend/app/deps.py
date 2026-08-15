"""BE-18: per-app store/llm_client access, via FastAPI's request.app.state.

A single-process, single-store app (docs/architecture.md) -- state lives
on `app.state` rather than a global module variable so tests can spin up
independent app instances (see tests/conftest_api.py's `make_app`)
without leaking state between them.
"""
from __future__ import annotations

from fastapi import Request

from app.llm.client import LLMClient
from app.store.memory_store import InMemoryStore


def get_store(request: Request) -> InMemoryStore:
    return request.app.state.store


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client
