"""The escalation ticket must be actionable by a human with NO transcript."""

from fakes import FakeAnthropic, final_turn, tool_use_turn

from support_agent.agent import run_conversation
from support_agent.backend import SessionContext, new_backend
from support_agent.tools import dispatch


def test_ticket_is_self_sufficient():
    ctx = SessionContext(verified_customer_id="CUST-1002")
    backend = new_backend()
    out = dispatch(
        "escalate_to_human",
        {
            "customer_ref": "CUST-1002",
            "order_id": "ORD-456",
            "reason": "Customer wants a full refund on ORD-456 (standing desk, damaged on "
            "arrival); amount is above the auto-approval limit so support cannot complete it.",
            "category": "refund_over_limit",
        },
        ctx=ctx,
        backend=backend,
    )
    ticket = out["ticket"]
    # who
    assert ticket["customer"]["name"] == "Bob Carter"
    assert ticket["customer"]["email"] == "bob.carter@example.com"
    # what order — snapshotted from the backend, not just an id
    assert ticket["order"]["order_id"] == "ORD-456"
    assert ticket["order"]["order_total"] == "742.00"
    # why — a real explanation, not "escalating..."
    assert len(ticket["reason"]) > 40
    assert ticket["ticket_id"].startswith("TKT-")
    assert ticket["status"] == "open"
    assert ticket["category"] == "refund_over_limit"


def test_ticket_when_identity_never_verified_keeps_the_raw_identifier():
    ctx = SessionContext()  # never verified
    out = dispatch(
        "escalate_to_human",
        {
            "customer_ref": "someone@example.com",
            "order_id": None,
            "reason": "Caller could not pass identity verification but insists their account "
            "was charged twice this month; needs a human to investigate the billing.",
            "category": "identity_unverifiable",
        },
        ctx=ctx,
        backend=new_backend(),
    )
    ticket = out["ticket"]
    assert ticket["customer"] == {"verified": False, "raw_identifier": "someone@example.com"}
    assert ticket["order"] is None


def test_thin_reason_is_rejected():
    out = dispatch(
        "escalate_to_human",
        {"customer_ref": "CUST-1002", "order_id": None, "reason": "escalating", "category": "other"},
        ctx=SessionContext(verified_customer_id="CUST-1002"),
        backend=new_backend(),
    )
    assert out["ok"] is False
    assert out["errorCategory"] == "validation"


def test_explicit_human_request_flows_to_a_ticket():
    client = FakeAnthropic(
        scripted=[
            tool_use_turn(("get_customer", {"full_name": "Bob Carter", "email": "bob.carter@example.com", "phone": None})),
            tool_use_turn(("lookup_order", {"order_id": "ORD-456", "customer_id": "CUST-1002"})),
            tool_use_turn(
                (
                    "escalate_to_human",
                    {
                        "customer_ref": "CUST-1002",
                        "order_id": "ORD-456",
                        "reason": "Customer explicitly asked to speak with a human about ORD-456.",
                        "category": "customer_requested_human",
                    },
                )
            ),
            final_turn("I've connected you with a specialist — ticket opened."),
        ]
    )
    result = run_conversation(
        client, "I want to talk to a human about ORD-456", ctx=SessionContext(), backend=new_backend()
    )
    assert len(result.tickets) == 1
    assert result.tickets[0]["category"] == "customer_requested_human"
