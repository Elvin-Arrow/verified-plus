"""TI-03: reusable hypothesis strategies for property-based tests (BE-02/03/08).

Kept in one place so BE-02 (geo.py), BE-03 (sort.py), and BE-08 (matching_service)
property tests draw from consistent, sane input distributions rather than each
inventing its own ad hoc float ranges.
"""
from __future__ import annotations

from hypothesis import strategies as st

from app.models.domain import Location

# Real-world latitude/longitude bounds.
latitudes = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False)
longitudes = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False)

locations = st.builds(Location, lat=latitudes, lng=longitudes)

# A tighter range clustered around the equator/prime-meridian, useful for
# geofence/centroid tests where extreme antipodal cases aren't the point.
local_latitudes = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)
local_longitudes = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)
local_locations = st.builds(Location, lat=local_latitudes, lng=local_longitudes)

urgency_scores = st.integers(min_value=1, max_value=5)
optional_urgency_scores = st.one_of(st.none(), urgency_scores)

device_counts = st.integers(min_value=1, max_value=20)

# (urgency, distinct_device_count) pairs, the sort.py tuple key domain.
sort_key_pairs = st.tuples(urgency_scores, device_counts)
