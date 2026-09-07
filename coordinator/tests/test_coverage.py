"""The coverage check compares the decomposition against the ticket."""

from coordinator.backend import TICKET_CONCERNS
from coordinator.coordinator import map_to_ticket
from coordinator.findings import coverage_gaps, extract_findings


def test_map_to_ticket_by_content_not_by_id():
    # the coordinator's own id is irrelevant; content decides
    assert map_to_ticket({"id": "c9", "detail": "refund ORD-123 damaged"}) == "c1"
    assert map_to_ticket({"id": "c2", "detail": "look up ORD-456 double charge"}) == "c2"
    assert map_to_ticket({"id": "c4", "detail": "is ORD-789 still returnable?"}) == "c3"
    assert map_to_ticket({"id": "c1", "detail": "handle the chargeback threat"}) == "c4"
    # a narrow coordinator's "verify identity" line is real work but not a ticket concern
    assert map_to_ticket({"id": "c1", "detail": "verify the customer for alice@example.com"}) is None


def test_narrow_style_decomposition_leaves_c4_unmapped():
    narrow = [
        {"id": "c1", "detail": "verify the customer"},
        {"id": "c2", "detail": "refund ORD-123, damaged"},
        {"id": "c3", "detail": "refund the duplicate charge on ORD-456"},
        {"id": "c4", "detail": "check whether ORD-789 shoes are returnable"},
    ]
    mapped = {map_to_ticket(c) for c in narrow} - {None}
    assert mapped == {"c1", "c2", "c3"}  # c4 (the chargeback threat) is dropped


def test_no_gaps_when_every_concern_has_a_finding():
    findings = [{"concern_id": c["id"]} for c in TICKET_CONCERNS]
    assert coverage_gaps(TICKET_CONCERNS, findings) == []


def test_dropped_concerns_are_gaps():
    findings = [{"concern_id": "c1"}, {"concern_id": "c3"}]
    assert [g["id"] for g in coverage_gaps(TICKET_CONCERNS, findings)] == ["c2", "c4"]


def test_extra_or_unknown_concern_ids_do_not_hide_a_gap():
    findings = [{"concern_id": "c1"}, {"concern_id": "c99"}, {"concern_id": "none"}]
    assert [g["id"] for g in coverage_gaps(TICKET_CONCERNS, findings)] == ["c2", "c3", "c4"]


def test_extract_findings_from_messy_prose():
    blob = (
        "Here are the results.\n"
        '[{"concern_id":"c3","claim":"still returnable","evidence":"45 days","source":"policy 2.2"}]\n'
        "Done."
    )
    got = extract_findings(blob)
    assert got == [{"concern_id": "c3", "claim": "still returnable",
                    "evidence": "45 days", "source": "policy 2.2"}]


def test_extract_findings_ignores_non_finding_arrays():
    blob = '["c1","c2"] then [{"concern_id":"c1","claim":"x"}]'
    got = extract_findings(blob)
    assert len(got) == 1 and got[0]["concern_id"] == "c1"
