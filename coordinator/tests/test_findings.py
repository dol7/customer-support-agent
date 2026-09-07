"""The claim / evidence / source contract."""

from coordinator.findings import extract_findings, is_attributable


def test_attributable_requires_all_four_fields():
    full = {"concern_id": "c1", "claim": "x", "evidence": "y", "source": "z"}
    assert is_attributable(full)
    for k in ("concern_id", "claim", "evidence", "source"):
        partial = dict(full, **{k: ""})
        assert not is_attributable(partial), k


def test_extract_handles_multiple_findings_in_one_array():
    blob = (
        'FINDINGS: [{"concern_id":"c1","claim":"refunded","evidence":"149.99","source":"process_refund"},'
        '{"concern_id":"c4","claim":"escalated","evidence":"ESC-9001","source":"escalate_to_human"}]'
    )
    got = extract_findings(blob)
    assert [f["concern_id"] for f in got] == ["c1", "c4"]


def test_extract_survives_no_findings():
    assert extract_findings("the coordinator said some words but no array") == []


def test_extract_keeps_source_verbatim():
    blob = '[{"concern_id":"c3","claim":"in window","evidence":"45 days if unworn","source":"policy 2.2"}]'
    (f,) = extract_findings(blob)
    assert f["source"] == "policy 2.2"
    assert f["evidence"] == "45 days if unworn"
