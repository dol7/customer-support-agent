"""In-memory stand-in for the retailer's backend.

This module owns the data and the money. It also owns the two hard rules that
must hold no matter what the model or a system prompt says:

* ``REFUND_AUTO_APPROVAL_LIMIT`` — the ceiling above which a refund needs a human.
* identity verification — ``verify_customer`` is the only thing that can populate
  a ``SessionContext.verified_customer_id``, and it only does so on a real match.

Nothing here reads a prompt. The number ``500`` appears in this file and nowhere
else in the package.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

# --- the hard rule that lives in code -------------------------------------------------
REFUND_AUTO_APPROVAL_LIMIT = Decimal("500.00")  # per refund, in the order's currency
REFUND_WINDOW_DAYS = 30

_DAY = 86_400


@dataclass
class Customer:
    customer_id: str
    full_name: str
    email: str
    phone: str  # E.164
    account_status: str  # "active" | "suspended" | "closed"


@dataclass
class OrderItem:
    sku: str
    name: str
    qty: int
    price: Decimal  # unit price


@dataclass
class Order:
    order_id: str
    customer_id: str
    status: str  # "processing" | "shipped" | "delivered" | "cancelled"
    currency: str
    items: list[OrderItem]
    placed_at: float
    delivered_at: float | None
    already_refunded: Decimal = Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return sum((i.price * i.qty for i in self.items), Decimal("0.00"))

    @property
    def refundable_amount(self) -> Decimal:
        return self.total - self.already_refunded


@dataclass
class Refund:
    refund_id: str
    order_id: str
    customer_id: str
    amount: Decimal
    reason: str
    status: str  # "completed" | "pending_human_approval"
    created_at: float


@dataclass
class SessionContext:
    """Per-conversation state. The identity gate reads ``verified_customer_id``.

    It starts as ``None`` and is only ever set by :meth:`Backend.verify_customer`.
    """

    verified_customer_id: str | None = None
    tickets: list[dict] = field(default_factory=list)


def _seeded_backend() -> "Backend":
    now = time.time()
    customers = [
        Customer("CUST-1001", "Alice Nguyen", "alice.nguyen@example.com", "+14155550101", "active"),
        Customer("CUST-1002", "Bob Carter", "bob.carter@example.com", "+14155550102", "active"),
        Customer("CUST-1003", "Dana Reed", "dana.reed@example.com", "+14155550103", "suspended"),
    ]
    orders = [
        Order(
            order_id="ORD-123",
            customer_id="CUST-1001",
            status="delivered",
            currency="USD",
            items=[
                OrderItem("SKU-BLND-01", "Countertop Blender", 1, Decimal("129.00")),
                OrderItem("SKU-CUP-04", "Spare Blending Cup", 2, Decimal("18.00")),
            ],
            placed_at=now - 12 * _DAY,
            delivered_at=now - 6 * _DAY,  # inside the 30-day window
        ),
        Order(
            order_id="ORD-456",
            customer_id="CUST-1002",
            status="delivered",
            currency="USD",
            items=[
                OrderItem("SKU-DESK-11", "Standing Desk Frame", 1, Decimal("742.00")),
            ],
            placed_at=now - 80 * _DAY,
            delivered_at=now - 74 * _DAY,  # outside the 30-day window
        ),
        Order(
            order_id="ORD-789",
            customer_id="CUST-1001",
            status="shipped",
            currency="USD",
            items=[OrderItem("SKU-MAT-02", "Anti-Fatigue Mat", 1, Decimal("64.00"))],
            placed_at=now - 3 * _DAY,
            delivered_at=None,
        ),
    ]
    return Backend(
        {c.customer_id: c for c in customers},
        {o.order_id: o for o in orders},
        {},
        now,
    )


@dataclass
class Backend:
    customers: dict[str, Customer]
    orders: dict[str, Order]
    refunds: dict[str, Refund]
    _now: float

    # --- identity -------------------------------------------------------------------
    def verify_customer(
        self, *, email: str | None, phone: str | None, full_name: str
    ) -> Customer | None:
        """Return the customer only if an identifier AND the name match, and the
        account is usable. This is the *only* path to a verified id."""
        want_name = full_name.strip().casefold()
        for c in self.customers.values():
            id_match = (
                (email is not None and c.email.casefold() == email.strip().casefold())
                or (phone is not None and c.phone == phone.strip())
            )
            if id_match and c.full_name.casefold() == want_name and c.account_status == "active":
                return c
        return None

    def open_order_count(self, customer_id: str) -> int:
        return sum(
            1
            for o in self.orders.values()
            if o.customer_id == customer_id and o.status in ("processing", "shipped")
        )

    # --- orders --------------------------------------------------------------------
    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def days_since_delivery(self, order: Order) -> float | None:
        if order.delivered_at is None:
            return None
        return (self._now - order.delivered_at) / _DAY

    # --- refunds ------------------------------------------------------------------
    def record_refund(
        self, *, order: Order, amount: Decimal, reason: str, status: str
    ) -> Refund:
        refund = Refund(
            refund_id=f"RF-{uuid.uuid4().hex[:10]}",
            order_id=order.order_id,
            customer_id=order.customer_id,
            amount=amount,
            reason=reason,
            status=status,
            created_at=self._now,
        )
        self.refunds[refund.refund_id] = refund
        if status == "completed":
            order.already_refunded += amount
        return refund


def new_backend() -> Backend:
    """Fresh seeded backend — one per conversation so runs do not bleed together."""
    return _seeded_backend()
