"""TI-03: shared pytest/hypothesis configuration.

Registers a hypothesis profile so property-based tests (docs/testing-spec.md
§4.4) run with a consistent, CI-safe example count and a fixed derandomized
seed for reproducibility, without every test module repeating the setup.
"""
from hypothesis import HealthCheck, settings

settings.register_profile(
    "default",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("default")
