"""Four error categories, distinct agent behaviour per category, lean payloads."""

import json

from fakes import FakeAnthropic, final_turn, tool_use_turn

from support_agent.agent import run_conversation
from support_agent.backend import SessionContext, new_backend
from support_agent.errors import tool_error
from support_agent.tools import FailMode, dispatch


def _verified_ctx():
    return SessionContext(verified_customer_id="CUST-1002")


def test_all_four_categories_have_the_right_retryability():
    assert tool_error("transient", "x")["isRetryable"] is True
    assert tool_error("validation", "x")["isRetryable"] is True
    assert tool_error("business", "x")["isRetryable"] is False
    assert tool_error("permission", "x")["isRetryable"] is False
    for cat in ("transient", "validation", "business", "permission"):
        e = tool_error(cat, "msg")
        assert set(e) == {"ok", "errorCategory", "isRetryable", "message"}
        assert e["ok"] is False


def test_business_error_is_produced_naturally_for_an_out_of_window_order():
    out = dispatch(
        "process_refund",
        {"customer_id": "CUST-1002", "order_id": "ORD-456", "amount": "100.00", "reason": "damaged"},
        ctx=_verified_ctx(),
        backend=new_backend(),
    )
    assert out["errorCategory"] == "business"
    assert out["isRetryable"] is False
    assert "window" in out["message"].lower()  # customer-facing explanation


def test_fail_mode_transient_then_succeeds_on_retry():
    fm = FailMode("transient")
    backend = new_backend()
    ctx = SessionContext(verified_customer_id="CUST-1001")
    first = dispatch("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}, ctx=ctx, backend=backend, fail_mode=fm)
    second = dispatch("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}, ctx=ctx, backend=backend, fail_mode=fm)
    assert first["errorCategory"] == "transient" and first["isRetryable"] is True
    assert second["ok"] is True


def test_fail_mode_validation_then_succeeds():
    fm = FailMode("validation")
    backend = new_backend()
    ctx = SessionContext(verified_customer_id="CUST-1001")
    bad = dispatch("process_refund", {"customer_id": "CUST-1001", "order_id": "ORD-123", "amount": "50.00", "reason": "damaged"}, ctx=ctx, backend=backend, fail_mode=fm)
    good = dispatch("process_refund", {"customer_id": "CUST-1001", "order_id": "ORD-123", "amount": "50.00", "reason": "damaged"}, ctx=ctx, backend=backend, fail_mode=fm)
    assert bad["errorCategory"] == "validation"
    assert good["ok"] is True


def test_payloads_are_lean_no_debug_padding():
    backend = new_backend()
    ctx = SessionContext(verified_customer_id="CUST-1001")
    out = dispatch("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}, ctx=ctx, backend=backend)
    allowed = {
        "ok", "order_id", "status", "placed_at", "delivered_at", "currency", "order_total",
        "refundable_amount", "already_refunded", "within_refund_window", "items",
    }
    assert set(out) <= allowed
    for item in out["items"]:
        assert set(item) == {"name", "qty", "unit_price"}  # no sku, no internal ids
    # nothing that smells like debug/metadata padding
    blob = json.dumps(out).lower()
    for bad in ("debug", "_meta", "trace", "raw_", "internal", "gateway"):
        assert bad not in blob


def test_agent_behaviour_differs_business_vs_permission():
    """business -> explain to the customer, no retry, no escalation.
       permission -> escalate, do not retry."""
    # business: model reads the error and just explains
    biz_client = FakeAnthropic(
        scripted=[
            tool_use_turn(("process_refund", {"customer_id": "CUST-1002", "order_id": "ORD-456", "amount": "100.00", "reason": "damaged"})),
            final_turn("Unfortunately ORD-456 is outside our 30-day return window, so I can't refund it."),
        ]
    )
    biz = run_conversation(biz_client, "refund ORD-456", ctx=_verified_ctx(), backend=new_backend())
    assert [c.name for c in biz.tool_calls] == ["process_refund"]
    assert biz.tickets == []

    # permission (over ceiling): model escalates
    perm_client = FakeAnthropic(
        scripted=[
            tool_use_turn(("process_refund", {"customer_id": "CUST-1002", "order_id": "ORD-456", "amount": "742.00", "reason": "damaged"})),
            tool_use_turn(("escalate_to_human", {"customer_ref": "CUST-1002", "order_id": "ORD-456", "reason": "Customer wants a full $742 refund on ORD-456 (damaged); above the auto-approval limit.", "category": "refund_over_limit"})),
            final_turn("That refund is above what I can approve, so I've opened a ticket for a specialist."),
        ]
    )
    perm = run_conversation(perm_client, "full refund ORD-456", ctx=_verified_ctx(), backend=new_backend())
    assert [c.name for c in perm.tool_calls] == ["process_refund", "escalate_to_human"]
    assert len(perm.tickets) == 1
