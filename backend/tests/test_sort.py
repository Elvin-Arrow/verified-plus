"""BE-03: lexicographic sort tie-breaking, per docs/testing-spec.md §3.1/§4.4."""
from hypothesis import given
from hypothesis import strategies as st

from app.models.domain import Location, Request
from app.sort import needs_manual_triage, sort_key, sorted_queue


def make_request(id_, urgency, device_id="dev_1"):
    return Request(
        id=id_,
        need_description="x",
        location=Location(0, 0),
        device_fingerprint_id=device_id,
        urgency_score=urgency,
    )


def resolve_single(r):
    return [r]


def resolve_cluster(cluster):
    return cluster  # a "cluster" fixture here is just list[Request]


def test_all_null_urgency_batch_is_all_triage():
    items = [make_request("r1", None), make_request("r2", None)]
    triage, rest = sorted_queue(items, resolve_single)
    assert len(triage) == 2
    assert rest == []


def test_tie_on_urgency_broken_by_distinct_device_count():
    cluster_a = [make_request("a1", 4, "dev_1")]
    cluster_b = [make_request("b1", 4, "dev_1"), make_request("b2", 4, "dev_2")]
    triage, rest = sorted_queue([cluster_a, cluster_b], resolve_cluster)
    assert triage == []
    assert rest[0] is cluster_b  # 2 distinct devices beats 1, urgency tied
    assert rest[1] is cluster_a


def test_urgency_wins_over_device_count_even_when_much_larger():
    high_urgency_one_device = [make_request("h1", 5, "dev_1")]
    low_urgency_many_devices = [
        make_request("l1", 3, "dev_1"),
        make_request("l2", 3, "dev_2"),
        make_request("l3", 3, "dev_3"),
    ]
    triage, rest = sorted_queue([low_urgency_many_devices, high_urgency_one_device], resolve_cluster)
    assert rest[0] is high_urgency_one_device
    assert rest[1] is low_urgency_many_devices


def test_single_member_item_vs_multi_member_event_compared_side_by_side():
    standalone = make_request("s1", 4)
    event_members = [make_request("e1", 4, "dev_1"), make_request("e2", 4, "dev_2")]
    triage, rest = sorted_queue([standalone, event_members], lambda i: resolve_single(i) if isinstance(i, Request) else resolve_cluster(i))
    assert rest[0] is event_members  # 2 devices beats 1 at tied urgency 4
    assert rest[1] is standalone


def test_empty_queue():
    triage, rest = sorted_queue([], resolve_single)
    assert triage == []
    assert rest == []


def test_needs_manual_triage_true_if_any_member_null():
    cluster = [make_request("a", 4), make_request("b", None)]
    assert needs_manual_triage(cluster, resolve_cluster) is True


def test_needs_manual_triage_false_when_all_scored():
    cluster = [make_request("a", 4), make_request("b", 2)]
    assert needs_manual_triage(cluster, resolve_cluster) is False


def test_sort_key_shape():
    r = make_request("a", 5, "dev_1")
    assert sort_key(r, resolve_single) == (5, 1)


# --- property-based (docs/testing-spec.md §4.4) ---

request_specs = st.lists(
    st.tuples(st.integers(min_value=1, max_value=5), st.integers(min_value=1, max_value=5)),
    min_size=1,
    max_size=15,
)


@given(request_specs)
def test_sorted_queue_output_is_non_increasing_and_lossless(specs):
    items = [make_request(f"r{i}", urgency, f"dev_{device}") for i, (urgency, device) in enumerate(specs)]
    triage, rest = sorted_queue(items, resolve_single)
    assert len(triage) + len(rest) == len(items)
    assert set(id(i) for i in triage) | set(id(i) for i in rest) == set(id(i) for i in items)
    keys = [sort_key(i, resolve_single) for i in rest]
    assert keys == sorted(keys, reverse=True)
