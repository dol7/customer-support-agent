"""Escalation ticket builder.

The contract: a human picks up the ticket with **no access to the chat
transcript**. So the ticket must carry, on its own, who the customer is, which
order (if any) is involved, and what needs doing and why the bot could not finish
it. We snapshot the customer and order from the backend rather than trusting
whatever ids happened to be in the arguments.
"""

from __future__ import annotations

import time
import uuid

from .backend import Backend

VALID_CATEGORIES = {
    "refund_over_limit",
    "identity_unverifiable",
    "customer_requested_human",
    "policy_exception",
    "other",
}


def build_ticket(
    backend: Backend,
    *,
    customer_ref: str,
    order_id: str | None,
    reason: str,
    category: str,
) -> dict:
    """Assemble a self-contained ticket. ``customer_ref`` is a verified
    ``CUST-...`` id when we have one, otherwise the raw identifier the customer
    gave (email / phone / name) so a human can still find them."""

    customer_block: dict
    cust = backend.customers.get(customer_ref)
    if cust is not None:
        customer_block = {
            "customer_id": cust.customer_id,
            "name": cust.full_name,
            "email": cust.email,
            "phone": cust.phone,
            "account_status": cust.account_status,
        }
    else:
        customer_block = {"verified": False, "raw_identifier": customer_ref}

    order_block: dict | None = None
    if order_id:
        order = backend.get_order(order_id)
        if order is not None:
            order_block = {
                "order_id": order.order_id,
                "status": order.status,
                "currency": order.currency,
                "order_total": f"{order.total:.2f}",
                "refundable_amount": f"{order.refundable_amount:.2f}",
                "already_refunded": f"{order.already_refunded:.2f}",
            }
        else:
            order_block = {"order_id": order_id, "note": "no such order in backend"}

    return {
        "ticket_id": f"TKT-{uuid.uuid4().hex[:8].upper()}",
        "created_at": _iso(time.time()),
        "status": "open",
        "category": category if category in VALID_CATEGORIES else "other",
        "customer": customer_block,
        "order": order_block,
        "reason": reason,
    }


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
