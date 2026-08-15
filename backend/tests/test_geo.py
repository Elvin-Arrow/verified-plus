"""BE-02: haversine correctness, geofence boundary cases, centroid math.

Per docs/testing-spec.md §3.1 geo.py row: known reference pairs, antipodal
points, 0 km (same point), and the exact 1.0km/1.5km boundary values used
elsewhere in the system.
"""
import math

import pytest
from hypothesis import given

from app.geo import centroid, haversine_km, within_radius
from app.models.domain import Location
from tests.strategies import local_locations, locations


def test_same_point_is_zero_km():
    p = Location(lat=12.34, lng=56.78)
    assert haversine_km(p, p) == pytest.approx(0.0, abs=1e-9)


def test_known_reference_pair_new_york_london():
    # Widely-cited reference great-circle distance ~5570 km.
    nyc = Location(lat=40.7128, lng=-74.0060)
    london = Location(lat=51.5074, lng=-0.1278)
    assert haversine_km(nyc, london) == pytest.approx(5570, rel=0.01)


def test_antipodal_points_are_half_earth_circumference():
    p = Location(lat=10.0, lng=20.0)
    antipode = Location(lat=-10.0, lng=20.0 - 180.0)
    assert haversine_km(p, antipode) == pytest.approx(math.pi * 6371.0, rel=1e-3)


def test_one_degree_latitude_is_about_111_km():
    a = Location(lat=0.0, lng=0.0)
    b = Location(lat=1.0, lng=0.0)
    assert haversine_km(a, b) == pytest.approx(111.19, rel=0.01)


def test_within_radius_boundary_exact_1km_is_inclusive():
    a = Location(lat=0.0, lng=0.0)
    b = Location(lat=1.0 / 111.19, lng=0.0)
    exact_distance = haversine_km(a, b)
    assert within_radius(a, b, exact_distance) is True


def test_within_radius_just_over_1km_excluded():
    a = Location(lat=0.0, lng=0.0)
    b = Location(lat=1.5 / 111.19, lng=0.0)  # ~1.5 km away
    assert within_radius(a, b, 1.0) is False


def test_within_radius_exact_1_5km_boundary_inclusive():
    a = Location(lat=0.0, lng=0.0)
    b = Location(lat=1.5 / 111.19, lng=0.0)
    exact_distance = haversine_km(a, b)
    assert within_radius(a, b, exact_distance) is True


def test_centroid_of_single_point_is_itself():
    p = Location(lat=5.0, lng=5.0)
    c = centroid([p])
    assert c.lat == pytest.approx(5.0)
    assert c.lng == pytest.approx(5.0)


def test_centroid_of_two_points_is_midpoint():
    a = Location(lat=0.0, lng=0.0)
    b = Location(lat=2.0, lng=4.0)
    c = centroid([a, b])
    assert c.lat == pytest.approx(1.0)
    assert c.lng == pytest.approx(2.0)


def test_centroid_of_empty_list_raises():
    with pytest.raises(ValueError):
        centroid([])


@given(locations)
def test_haversine_is_symmetric(loc):
    other = Location(lat=0.0, lng=0.0)
    assert haversine_km(loc, other) == pytest.approx(haversine_km(other, loc), abs=1e-6)


@given(locations)
def test_haversine_never_negative(loc):
    other = Location(lat=0.0, lng=0.0)
    assert haversine_km(loc, other) >= 0.0


@given(local_locations, local_locations, local_locations)
def test_centroid_lies_within_bounding_box_of_inputs(a, b, c):
    result = centroid([a, b, c])
    eps = 1e-9
    assert min(a.lat, b.lat, c.lat) - eps <= result.lat <= max(a.lat, b.lat, c.lat) + eps
    assert min(a.lng, b.lng, c.lng) - eps <= result.lng <= max(a.lng, b.lng, c.lng) + eps
