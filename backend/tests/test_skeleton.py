"""TI-01: sanity check that the pytest project skeleton is wired up correctly."""


def test_skeleton_collects_and_runs():
    assert 1 + 1 == 2


def test_app_package_importable():
    import app  # noqa: F401
