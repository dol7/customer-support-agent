"""The live-demo shape: one message, two jobs, one consolidated reply."""

from decimal import Decimal

from fakes import FakeAnthropic, final_turn, tool_use_turn

from support_agent.agent import run_conversation
from support_agent.backend import SessionContext, new_backend


def test_refund_one_order_and_report_status_of_another_in_a_single_reply():
    backend = new_backend()
    client = FakeAnthropic(
        scripted=[
            tool_use_turn(
                ("get_customer", {"full_name": "Alice Nguyen", "email": "alice.nguyen@example.com", "phone": None})
            ),
            # model fans out both order reads in one turn
            tool_use_turn(
                ("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}),
                ("lookup_order", {"order_id": "ORD-789", "customer_id": "CUST-1001"}),
            ),
            tool_use_turn(
                ("process_refund", {"customer_id": "CUST-1001", "order_id": "ORD-123", "amount": "165.00", "reason": "damaged"})
            ),
            final_turn(
                "All set, Alice. I've refunded $165.00 for the cracked blender jug on ORD-123 "
                "(RF-...), and ORD-789 is currently shipped and on its way to you."
            ),
        ]
    )
    result = run_conversation(
        client,
        "refund ORD-123 (cracked jug) and where is ORD-789?",
        ctx=SessionContext(),
        backend=backend,
    )

    assert result.stop_reason == "end_turn"
    assert [c.name for c in result.tool_calls] == [
        "get_customer",
        "lookup_order",
        "lookup_order",
        "process_refund",
    ]
    # the refund really happened in the backend
    assert backend.get_order("ORD-123").already_refunded == Decimal("165.00")
    assert len(backend.refunds) == 1
    # one reply, covering both jobs
    assert result.reply.count("ORD-123") >= 1 and "ORD-789" in result.reply
    assert result.messages[-1]["role"] == "assistant"
