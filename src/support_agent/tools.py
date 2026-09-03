"""The four tools: definitions, dispatch, and the in-code enforcement hook.

Tools are declared with exactly the three fields the Messages API takes —
``name``, ``description``, ``input_schema`` (plus ``strict`` for argument
validation). No MCP server; ``dispatch`` runs the Python behind each name.

``get_customer`` and ``lookup_order`` are close enough to be misrouted if the
descriptions are thin. The fix here is the descriptions themselves — each names
its lookup key, its precondition, its output, and when to use the *other* one.

Enforcement (identity gate, $500 ceiling) is a pre-exec hook in ``dispatch`` plus
a second check inside ``_process_refund``. It does not depend on the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .backend import REFUND_AUTO_APPROVAL_LIMIT, REFUND_WINDOW_DAYS, Backend, SessionContext
from .errors import tool_error
from .escalation import build_ticket

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+\d{8,15}$")
_ORDER_RE = re.compile(r"^ORD-\d+$")
_REFUND_REASONS = {"damaged", "not_received", "wrong_item", "no_longer_wanted", "billing_error"}
_GATED_TOOLS = {"lookup_order", "process_refund"}


# --------------------------------------------------------------------------------------
# Tool definitions
# --------------------------------------------------------------------------------------
TOOL_DEFS: list[dict] = [
    {
        "name": "get_customer",
        "description": (
            "Resolve and verify WHO a person is, from their own identifiers. This is the "
            "identity step: on a match it returns the customer_id that lookup_order and "
            "process_refund both require, and marks the session verified.\n\n"
            "Lookup key: a personal identifier — email OR phone — PLUS the full name to "
            "match against. It cannot look someone up from an order number.\n\n"
            "Inputs:\n"
            "  full_name (string, required) — the customer's full name, e.g. \"Alice Nguyen\".\n"
            "  email (string or null) — RFC-5322 address, e.g. \"alice.nguyen@example.com\". "
            "Pass null if the customer gave a phone instead.\n"
            "  phone (string or null) — E.164, \"+\" then digits, e.g. \"+14155550101\". "
            "Pass null if the customer gave an email instead.\n"
            "Provide exactly one of email/phone; the other must be null.\n\n"
            "Output: { ok, customer_id, name, email, verified, account_status, open_order_count }. "
            "On no match: a business error (identity could not be verified).\n\n"
            "When NOT to use this tool:\n"
            "  - You already verified this customer earlier in the conversation — reuse that "
            "customer_id, do not verify again.\n"
            "  - You want the status, items, totals, or refund-eligibility of a specific order "
            "— that is lookup_order.\n"
            "  - The customer gave only an order number and no email or phone — you cannot "
            "verify identity from an order number; ask them for an email or phone first."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
            },
            "required": ["full_name", "email", "phone"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_order",
        "description": (
            "Fetch the facts of ONE specific order that is already identified by its order "
            "number. Read-only: it moves no money and changes nothing.\n\n"
            "Lookup key: the order_id. Precondition: the session must already be verified — "
            "pass the customer_id from get_customer. Without a valid verified customer_id "
            "this tool refuses.\n\n"
            "Inputs:\n"
            "  order_id (string, required) — \"ORD-\" followed by digits, e.g. \"ORD-123\".\n"
            "  customer_id (string, required) — the verified id from get_customer, e.g. "
            "\"CUST-1001\".\n\n"
            "Output: { ok, order_id, status, placed_at, delivered_at, currency, order_total, "
            "refundable_amount, already_refunded, within_refund_window, items:[{name, qty, "
            "unit_price}] }. Unknown order or one that does not belong to this customer: a "
            "business error.\n\n"
            "When NOT to use this tool:\n"
            "  - To find out who the customer is, or to verify them — that is get_customer. "
            "This tool assumes identity is already established.\n"
            "  - To list all of a customer's orders — not supported; you need the specific "
            "order number from the customer.\n"
            "  - To issue or approve a refund — that is process_refund. This tool only reads."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "customer_id": {"type": "string"},
            },
            "required": ["order_id", "customer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "process_refund",
        "description": (
            "Issue a refund against a verified customer's order. This moves money.\n\n"
            "Precondition: session verified (pass the get_customer customer_id). Call "
            "lookup_order first so you know the currency and the refundable_amount.\n\n"
            "Inputs:\n"
            "  customer_id (string, required) — verified id from get_customer.\n"
            "  order_id (string, required) — \"ORD-\" + digits.\n"
            "  amount (string, required) — decimal with two places, in the order's currency, "
            "e.g. \"129.00\". Must be > 0 and <= refundable_amount.\n"
            "  reason (string, required) — one of: damaged, not_received, wrong_item, "
            "no_longer_wanted, billing_error.\n\n"
            "Output: { ok, refund_id, amount, status } where status is \"completed\". "
            "Possible errors: validation (bad amount/reason format), business (order outside "
            "the return window, amount exceeds refundable_amount), permission (amount above "
            "the auto-approval limit — a human must approve; do NOT retry, call "
            "escalate_to_human).\n\n"
            "When NOT to use this tool:\n"
            "  - Identity is not verified yet — call get_customer.\n"
            "  - You only want to check whether a refund already happened — that is "
            "lookup_order (already_refunded).\n"
            "  - The customer asked for a human, or a previous call returned a permission "
            "error — call escalate_to_human instead of retrying."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "order_id": {"type": "string"},
                "amount": {"type": "string"},
                "reason": {"type": "string", "enum": sorted(_REFUND_REASONS)},
            },
            "required": ["customer_id", "order_id", "amount", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the case to a human agent with a ticket they can act on WITHOUT seeing "
            "this conversation. Use it when you cannot finish within the rules, or the "
            "customer wants a person.\n\n"
            "Inputs:\n"
            "  customer_ref (string, required) — the verified customer_id if you have one; "
            "otherwise the raw identifier the customer gave (email, phone, or name) so a "
            "human can still find them.\n"
            "  order_id (string or null) — the order in question, \"ORD-\" + digits, or null "
            "if none applies.\n"
            "  reason (string, required) — what the customer wants AND why you could not "
            "complete it. Write it for someone with zero context.\n"
            "  category (string, required) — one of: refund_over_limit, identity_unverifiable, "
            "customer_requested_human, policy_exception, other.\n\n"
            "Output: { ok, ticket_id, status, ticket } — the ticket already contains a "
            "customer snapshot and (if order_id was given) an order snapshot.\n\n"
            "When NOT to use this tool:\n"
            "  - You can still resolve the request yourself within the rules.\n"
            "  - You just need order data — that is lookup_order."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_ref": {"type": "string"},
                "order_id": {"type": ["string", "null"]},
                "reason": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": [
                        "refund_over_limit",
                        "identity_unverifiable",
                        "customer_requested_human",
                        "policy_exception",
                        "other",
                    ],
                },
            },
            "required": ["customer_ref", "order_id", "reason", "category"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOL_DEFS}


# --------------------------------------------------------------------------------------
# FAIL_MODE — inject one deterministic failure so a single run can show every category
# --------------------------------------------------------------------------------------
@dataclass
class FailMode:
    """Mutable so ``*_once`` modes can fire exactly once."""

    mode: str = "none"
    _fired: bool = False

    VALID = ("none", "transient", "validation", "business", "permission")

    def __post_init__(self) -> None:
        if self.mode not in self.VALID:
            raise ValueError(f"unknown fail mode {self.mode!r}; pick from {self.VALID}")

    def take(self, tool_name: str) -> dict | None:
        """Return an injected error dict the first time it applies, else None."""
        if self.mode == "none" or self._fired:
            return None
        hit = {
            "transient": (
                tool_name == "lookup_order",
                lambda: tool_error("transient", "order service timed out; retry in a moment"),
            ),
            "validation": (
                tool_name == "process_refund",
                lambda: tool_error(
                    "validation",
                    'amount must be a decimal string with two places, e.g. "129.00"',
                ),
            ),
            "business": (
                tool_name == "process_refund",
                lambda: tool_error(
                    "business",
                    "This order was delivered more than 30 days ago and is outside the "
                    "return window, so it is not eligible for a refund.",
                ),
            ),
            "permission": (
                tool_name == "process_refund",
                lambda: tool_error(
                    "permission",
                    "This refund exceeds the amount support can approve directly; a "
                    "human must approve it.",
                ),
            ),
        }[self.mode]
        applies, make = hit
        if not applies:
            return None
        self._fired = True
        return make()


# --------------------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------------------
def dispatch(
    name: str,
    tool_input: dict,
    *,
    ctx: SessionContext,
    backend: Backend,
    fail_mode: FailMode | None = None,
) -> dict:
    """Run the tool named ``name``. Always returns a dict; never raises for a
    tool-level problem (bad input, business rule, permission). Raises only for a
    genuinely unknown tool name, which is a wiring bug."""
    if name not in TOOL_NAMES:
        raise KeyError(f"unknown tool: {name!r}")

    fail_mode = fail_mode or FailMode()

    # --- enforcement hook: runs BEFORE the tool body -------------------------------
    gate = _identity_gate(name, tool_input, ctx)
    if gate is not None:
        return gate
    if name == "process_refund":
        ceiling = _ceiling_check(tool_input)
        if ceiling is not None:
            return ceiling

    # --- deterministic failure injection for the demo -----------------------------
    injected = fail_mode.take(name)
    if injected is not None:
        return injected

    if name == "get_customer":
        return _get_customer(tool_input, ctx=ctx, backend=backend)
    if name == "lookup_order":
        return _lookup_order(tool_input, ctx=ctx, backend=backend)
    if name == "process_refund":
        return _process_refund(tool_input, ctx=ctx, backend=backend)
    return _escalate_to_human(tool_input, ctx=ctx, backend=backend)


def _identity_gate(name: str, tool_input: dict, ctx: SessionContext) -> dict | None:
    """Hard rule #1: no order operation before identity is verified, and only for
    the customer who was verified."""
    if name not in _GATED_TOOLS:
        return None
    if ctx.verified_customer_id is None:
        return tool_error(
            "permission",
            "Identity is not verified for this session. Call get_customer with the "
            "customer's name and email or phone first.",
        )
    if tool_input.get("customer_id") != ctx.verified_customer_id:
        return tool_error(
            "permission",
            "The customer_id does not match the verified customer for this session.",
        )
    return None


def _ceiling_check(tool_input: dict) -> dict | None:
    """Hard rule #2: refunds above the auto-approval limit need a human."""
    try:
        amount = Decimal(str(tool_input.get("amount")))
    except (InvalidOperation, TypeError):
        return None  # let _process_refund return the validation error
    if amount > REFUND_AUTO_APPROVAL_LIMIT:
        return tool_error(
            "permission",
            f"A refund of {amount:.2f} exceeds the amount support can approve directly. "
            f"A human must approve it — escalate instead of retrying.",
        )
    return None


# --------------------------------------------------------------------------------------
# Tool bodies — each returns a LEAN payload (only fields Claude needs on later turns)
# --------------------------------------------------------------------------------------
def _get_customer(tool_input: dict, *, ctx: SessionContext, backend: Backend) -> dict:
    full_name = (tool_input.get("full_name") or "").strip()
    email = tool_input.get("email")
    phone = tool_input.get("phone")

    if not full_name:
        return tool_error("validation", "full_name is required")
    if email is None and phone is None:
        return tool_error("validation", "provide an email or a phone")
    if email is not None and not _EMAIL_RE.match(email.strip()):
        return tool_error("validation", f"email is not a valid address: {email!r}")
    if phone is not None and not _PHONE_RE.match(phone.strip()):
        return tool_error("validation", f'phone must be E.164 ("+" then 8-15 digits): {phone!r}')

    customer = backend.verify_customer(email=email, phone=phone, full_name=full_name)
    if customer is None:
        return tool_error(
            "business",
            "We could not verify this customer. The name and email or phone do not match "
            "an active account. Ask the customer to confirm the details on the account.",
        )

    ctx.verified_customer_id = customer.customer_id  # the ONLY place this is set
    return {
        "ok": True,
        "customer_id": customer.customer_id,
        "name": customer.full_name,
        "email": customer.email,
        "verified": True,
        "account_status": customer.account_status,
        "open_order_count": backend.open_order_count(customer.customer_id),
    }


def _lookup_order(tool_input: dict, *, ctx: SessionContext, backend: Backend) -> dict:
    order_id = (tool_input.get("order_id") or "").strip()
    if not _ORDER_RE.match(order_id):
        return tool_error("validation", f'order_id must look like "ORD-123": {order_id!r}')

    order = backend.get_order(order_id)
    if order is None or order.customer_id != ctx.verified_customer_id:
        return tool_error(
            "business",
            f"No order {order_id} is associated with this customer.",
        )

    days = backend.days_since_delivery(order)
    within_window = days is not None and days <= REFUND_WINDOW_DAYS
    return {
        "ok": True,
        "order_id": order.order_id,
        "status": order.status,
        "placed_at": _iso(order.placed_at),
        "delivered_at": _iso(order.delivered_at) if order.delivered_at else None,
        "currency": order.currency,
        "order_total": f"{order.total:.2f}",
        "refundable_amount": f"{order.refundable_amount:.2f}",
        "already_refunded": f"{order.already_refunded:.2f}",
        "within_refund_window": within_window,
        "items": [
            {"name": i.name, "qty": i.qty, "unit_price": f"{i.price:.2f}"} for i in order.items
        ],
    }


def _process_refund(tool_input: dict, *, ctx: SessionContext, backend: Backend) -> dict:
    order_id = (tool_input.get("order_id") or "").strip()
    reason = (tool_input.get("reason") or "").strip()
    raw_amount = tool_input.get("amount")

    if not _ORDER_RE.match(order_id):
        return tool_error("validation", f'order_id must look like "ORD-123": {order_id!r}')
    if reason not in _REFUND_REASONS:
        return tool_error("validation", f"reason must be one of {sorted(_REFUND_REASONS)}")
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError):
        return tool_error(
            "validation", f'amount must be a decimal string like "129.00": {raw_amount!r}'
        )
    if amount <= 0:
        return tool_error("validation", "amount must be greater than 0")

    order = backend.get_order(order_id)
    if order is None or order.customer_id != ctx.verified_customer_id:
        return tool_error("business", f"No order {order_id} is associated with this customer.")

    # Hard rule #2, again — defence in depth, independent of the pre-exec hook.
    if amount > REFUND_AUTO_APPROVAL_LIMIT:
        return tool_error(
            "permission",
            f"A refund of {amount:.2f} exceeds the amount support can approve directly. "
            f"A human must approve it.",
        )

    days = backend.days_since_delivery(order)
    if days is None:
        return tool_error(
            "business",
            f"Order {order_id} has not been delivered yet, so it cannot be refunded.",
        )
    if days > REFUND_WINDOW_DAYS:
        return tool_error(
            "business",
            f"Order {order_id} was delivered about {int(days)} days ago, outside the "
            f"{REFUND_WINDOW_DAYS}-day return window, so it is not eligible for a refund.",
        )
    if amount > order.refundable_amount:
        return tool_error(
            "business",
            f"The refundable amount on {order_id} is {order.refundable_amount:.2f}; "
            f"{amount:.2f} is more than that.",
        )

    refund = backend.record_refund(order=order, amount=amount, reason=reason, status="completed")
    return {
        "ok": True,
        "refund_id": refund.refund_id,
        "amount": f"{refund.amount:.2f}",
        "currency": order.currency,
        "status": refund.status,
    }


def _escalate_to_human(tool_input: dict, *, ctx: SessionContext, backend: Backend) -> dict:
    customer_ref = (tool_input.get("customer_ref") or "").strip()
    reason = (tool_input.get("reason") or "").strip()
    category = (tool_input.get("category") or "other").strip()
    order_id = tool_input.get("order_id")

    if not customer_ref:
        return tool_error("validation", "customer_ref is required")
    if len(reason) < 15:
        return tool_error(
            "validation",
            "reason is too thin — state what the customer wants and why you could not "
            "finish, for someone with no context",
        )

    ticket = build_ticket(
        backend,
        customer_ref=customer_ref,
        order_id=order_id,
        reason=reason,
        category=category,
    )
    ctx.tickets.append(ticket)
    return {"ok": True, "ticket_id": ticket["ticket_id"], "status": ticket["status"], "ticket": ticket}


def _iso(ts: float) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
