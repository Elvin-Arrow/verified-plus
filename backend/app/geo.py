"""BE-02: haversine distance, geofence filtering, centroid recompute.

Implements docs/design.md §4.2/§4.4 geometry helpers and the FR-202/FR-205
distance/span checks. Pure functions, no store access.
"""
from __future__ import annotations

import math

from app.models.domain import Location

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: Location, b: Location) -> float:
    """Great-circle distance between two lat/lng points, in kilometers."""
    lat1, lng1 = math.radians(a.lat), math.radians(a.lng)
    lat2, lng2 = math.radians(b.lat), math.radians(b.lng)
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    h = min(1.0, max(0.0, h))  # guard tiny float overshoot past [0, 1] for asin
    c = 2 * math.asin(math.sqrt(h))
    return EARTH_RADIUS_KM * c


def within_radius(a: Location, b: Location, radius_km: float) -> bool:
    """Inclusive boundary check: exactly `radius_km` away counts as within."""
    return haversine_km(a, b) <= radius_km


def centroid(locations: list[Location]) -> Location:
    """Simple arithmetic-mean centroid — adequate at demo scale/span (<= a
    few km), where equirectangular averaging error is negligible."""
    if not locations:
        raise ValueError("centroid() requires at least one location")
    avg_lat = sum(loc.lat for loc in locations) / len(locations)
    avg_lng = sum(loc.lng for loc in locations) / len(locations)
    return Location(lat=avg_lat, lng=avg_lng)
