"""TI-03: sanity checks that the hypothesis strategies/scaffolding actually work."""
from hypothesis import given

from tests.strategies import locations, sort_key_pairs, urgency_scores


@given(urgency_scores)
def test_urgency_scores_in_range(score):
    assert 1 <= score <= 5


@given(locations)
def test_locations_in_valid_lat_lng_range(loc):
    assert -90.0 <= loc.lat <= 90.0
    assert -180.0 <= loc.lng <= 180.0


@given(sort_key_pairs)
def test_sort_key_pairs_shape(pair):
    urgency, device_count = pair
    assert 1 <= urgency <= 5
    assert device_count >= 1
