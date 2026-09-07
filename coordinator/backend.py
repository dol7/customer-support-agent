"""The Northwind stand-in backend: three dicts and a refund log.

Everything here is deliberately small — the assignment is about control flow
between agents, not about a realistic data layer. The one customer, three orders
and five policy clauses are enough to carry the four-concern ticket.
"""

from __future__ import annotations

from .config import days_ago

CUSTOMERS: dict[str, dict] = {
    "alice@example.com": {
        "customer_id": "CUST-001",
        "name": "Alice Chen",
        "email": "alice@example.com",
        "tier": "Gold",
    },
}

ORDERS: dict[str, dict] = {
    # c1: damaged electronics, 17 days out (inside the 14-day electronics window? no
    # — but the damaged condition drives a refund, and it is under the ceiling)
    "ORD-123": {
        "customer_id": "CUST-001", "sku": "EL-4402", "amount": 149.99,
        "status": "delivered", "delivered_on": days_ago(17),
        "condition": "damaged", "charges": 1,
    },
    # c2: charged twice — a real duplicate to find
    "ORD-456": {
        "customer_id": "CUST-001", "sku": "AP-1180", "amount": 89.00,
        "status": "delivered", "delivered_on": days_ago(23),
        "condition": "ok", "charges": 2,
    },
    # c3 / hook demo: footwear 40 days out — past the 30-day standard window
    # (2.1) but inside the 45-day footwear window (2.2) because it is unworn.
    # Amount is over the $500 ceiling, for the hook demo.
    "ORD-789": {
        "customer_id": "CUST-001", "sku": "FW-2201", "amount": 812.40,
        "status": "delivered", "delivered_on": days_ago(40),
        "condition": "unworn", "charges": 1,
    },
}

POLICY: dict[str, str] = {
    "2.1": "Standard return window: 30 calendar days from delivery date.",
    "2.2": "Footwear and apparel may be returned within 45 days if unworn with "
           "tags attached.",
    "2.3": "Electronics return window: 14 days.",
    "3.4": "Auto-escalate to Tier 2 if the customer mentions lawyer, BBB, "
           "chargeback, or social media.",
    "3.5": "Refund requests over $500 require Tier 2 approval.",
    "5.2": "Duplicate charges: once a second charge for one order is confirmed, "
           "refund the extra charge to the original payment method. No further "
           "approval is needed below the section 3.5 ceiling.",
}

# process_refund appends here. Tests and demos assert on it directly.
REFUND_LOG: list[dict] = []

# The four concerns in ALICE_TICKET, as ground truth for the coverage check.
# The coverage check compares the coordinator's *own* decomposition against the
# ticket; this list is what "the ticket" means when we score coverage.
TICKET_CONCERNS = [
    {"id": "c1", "kind": "refund", "order_id": "ORD-123",
     "detail": "ORD-123 arrived damaged; wants a refund."},
    {"id": "c2", "kind": "billing", "order_id": "ORD-456",
     "detail": "ORD-456 was charged to the card twice."},
    {"id": "c3", "kind": "policy", "order_id": "ORD-789",
     "detail": "Bought shoes on ORD-789 ~40 days ago; can they still be returned?"},
    {"id": "c4", "kind": "escalation", "order_id": None,
     "detail": "Threatening to file a chargeback if not resolved today."},
]

ALICE_TICKET = (
    "I'm alice@example.com. "
    "ORD-123 arrived damaged and I want a refund. "
    "ORD-456 got charged to my card twice. "
    "I bought shoes on ORD-789 forty days ago. Can I still return them? "
    "If this isn't sorted today I'm filing a chargeback."
)


def reset() -> None:
    REFUND_LOG.clear()
