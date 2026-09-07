"""Tool payload shapes, structured errors, and the fault injections."""

import asyncio
import json

from coordinator import backend
from coordinator.tools import (
    create_northwind,
    get_customer,
    process_refund,
    read_policy,
    _lookup_order_bare,
    _lookup_order_healthy,
    _lookup_order_structured,
)


def _payload(result):
    return json.loads(result["content"][0]["text"])


def run(coro):
    return asyncio.run(coro)


def test_get_customer_ok_and_validation_error():
    assert _payload(run(get_customer.handler({"email": "alice@example.com"})))["customer_id"] == "CUST-001"
    bad = run(get_customer.handler({"email": "nobody@example.com"}))
    assert bad["is_error"] is True
    assert _payload(bad)["errorCategory"] == "validation"
    assert _payload(bad)["isRetryable"] is False


def test_lookup_order_is_lean():
    out = _payload(run(_lookup_order_healthy.handler({"order_id": "ORD-456"})))
    assert out["charges"] == 2 and out["order_id"] == "ORD-456"
    assert set(out) == {"order_id", "customer_id", "sku", "amount", "status",
                        "delivered_on", "condition", "charges"}


def test_read_policy_hit_is_lean():
    body = _payload(run(read_policy.handler({"section": "2.2"})))
    assert body == {"section": "2.2", "found": True,
                    "text": "Footwear and apparel may be returned within 45 days "
                            "if unworn with tags attached."}


def test_read_policy_missing_section_is_a_valid_empty_with_the_index():
    out = run(read_policy.handler({"section": "9.9"}))
    assert "is_error" not in out  # NOT an error
    body = _payload(out)
    assert body["found"] is False and body["text"] is None
    assert body["available_sections"] == ["2.1", "2.2", "2.3", "3.4", "3.5", "5.2"]


def test_process_refund_writes_the_log():
    backend.reset()
    run(process_refund.handler({"order_id": "ORD-123", "amount": 10.0}))
    assert backend.REFUND_LOG == [{"order_id": "ORD-123", "amount": 10.0}]


def test_bare_fault_is_two_words_and_unstructured():
    fn = _lookup_order_bare()
    out = run(fn.handler({"order_id": "ORD-456"}))
    assert out["is_error"] is True
    assert out["content"][0]["text"] == "Lookup failed."
    # healthy order still works through the faulted server
    assert _payload(run(fn.handler({"order_id": "ORD-123"})))["order_id"] == "ORD-123"


def test_structured_fault_carries_context_partial_and_alternatives():
    fn = _lookup_order_structured()
    out = run(fn.handler({"order_id": "ORD-456"}))
    body = _payload(out)
    assert out["is_error"] is True
    assert body["errorCategory"] == "transient" and body["isRetryable"] is True
    assert body["attempted"] == "lookup_order(ORD-456)"
    assert body["partialResults"][0]["concern_id"] == "c2"
    assert any("flag c2" in a for a in body["alternatives"])


def test_create_northwind_variants_build():
    for fault in (None, "bare", "structured"):
        srv = create_northwind(fault)
        assert srv is not None


def test_scoped_server_only_mounts_the_named_tools():
    """The hard tool boundary: run_agent builds each specialist a server that
    carries only that specialist's tool(s). End-to-end proof is in
    transcripts/context_isolation.md — the scoped policy-analyst cannot look up
    the order and says so."""
    from coordinator.agents import AGENTS
    from coordinator.tools import northwind_tool_names

    for name, agent in AGENTS.items():
        short = [t.rsplit("__", 1)[-1] for t in agent.tools]
        assert northwind_tool_names(short) == short, name
        assert "process_refund" not in short or name == "refund-processor"
    assert len(northwind_tool_names()) == 5
