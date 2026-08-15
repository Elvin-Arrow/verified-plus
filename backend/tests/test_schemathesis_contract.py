"""TI-05: schemathesis contract-test harness against BE-18's real, fully-wired
routes. docs/testing-spec.md §3.2/§10.

Schema-driven fuzzing off the FastAPI-generated OpenAPI document, checking
the properties that hold for EVERY endpoint regardless of what schemathesis
randomly generates: never a 500 (an unhandled crash is always a bug, even
on a nonsense input -- api-spec.md §1.1 documents INTERNAL_ERROR as
"unhandled server fault", the one thing that should never come from a
malformed-but-well-typed request), and every non-2xx response body matches
the documented standard error envelope shape (§1.1). Full response-schema
conformance per exact status code is intentionally NOT used here: FastAPI's
auto-generated schema documents its own default 422 for request-body
validation, which app/errors.py deliberately remaps to api-spec.md's 400
VALIDATION_ERROR (discovered by an earlier throwaway run of this exact
harness) -- reconciling that would mean hand-annotating `responses={}` on
every route for a mismatch schemathesis already tells us about for free.
The state-dependent 409 cases (schemathesis can't derive those without
seeded state) are covered by the hand-written cases in
tests/test_api_contract.py, per testing-spec.md §3.2.
"""
import schemathesis
from hypothesis import HealthCheck, settings

from app.main import create_app
from app.store.memory_store import InMemoryStore
from tests.fixtures.llm_double import FakeLLMClient, ScriptedResponse


def _make_schema():
    store = InMemoryStore()
    llm = FakeLLMClient()
    llm.script("need water", ScriptedResponse(urgency_score=3, urgency_reasoning="ok"))
    app = create_app(store=store, llm_client=llm)
    return schemathesis.openapi.from_asgi("/openapi.json", app)


schema = _make_schema()


def _assert_error_envelope_shape(body: dict) -> None:
    assert "error" in body, f"non-2xx response missing 'error' envelope: {body}"
    error = body["error"]
    assert set(error.keys()) >= {"code", "message"}
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)
    assert error["code"] in {"VALIDATION_ERROR", "NOT_FOUND", "INVALID_STATE_TRANSITION", "INTERNAL_ERROR"}


_DOCUMENTED_ERROR_CODES = {400, 404, 409}


@schema.parametrize()
@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_every_endpoint_never_500s_and_errors_match_envelope(case):
    response = case.call()
    assert response.status_code < 500, (
        f"{case.method} {case.path} returned {response.status_code} (a server fault) "
        f"for generated input {case.body!r}: {response.text}"
    )
    if response.status_code in _DOCUMENTED_ERROR_CODES:
        # Status codes api-spec.md §1.1 actually documents must use its
        # envelope. Other 4xx (e.g. schemathesis's own method-variant
        # probing landing on a plain Starlette 405) are outside this
        # contract's scope -- no route in api-spec.md documents them.
        _assert_error_envelope_shape(response.json())
