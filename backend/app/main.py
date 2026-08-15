"""BE-18: FastAPI app, router registration, CORS, startup config load.
docs/design.md §2.

`create_app` is a factory so tests (and the seed/replay flow) can build
an isolated app instance with its own InMemoryStore/LLMClient rather than
sharing global module state (docs/design.md §3's coarse-lock model is
per-store, not per-process).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import register_error_handlers
from app.llm.client import HostedLLMClient, LLMClient
from app.routers import events, quarantine, queues, requests, seed
from app.store.memory_store import InMemoryStore


def create_app(store: InMemoryStore | None = None, llm_client: LLMClient | None = None) -> FastAPI:
    app = FastAPI(title="Aid Request Triage & Trust Tool API", version="0.1.0")
    app.state.store = store or InMemoryStore()
    app.state.llm_client = llm_client or HostedLLMClient()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # hackathon scope -- no auth (api-spec.md §1)
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(requests.router)
    app.include_router(events.router)
    app.include_router(queues.router)
    app.include_router(quarantine.router)
    app.include_router(seed.router)

    return app


app = create_app()
