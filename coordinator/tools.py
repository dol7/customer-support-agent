"""The five Northwind tools, as an in-process SDK MCP server.

``create_northwind(fault=...)`` builds the server. ``fault`` injects one
deterministic failure into ``lookup_order`` for ORD-456, in two shapes:

* ``"bare"``       — ``is_error`` with two words. The coordinator cannot choose
                     between retry, skip and escalate from this.
* ``"structured"`` — ``err("transient", True, attempted=, partialResults=,
                     alternatives=)``. Everything the coordinator needs to
                     recover is in the payload.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from .backend import CUSTOMERS, ORDERS, POLICY, REFUND_LOG
from .mcp_helpers import err, ok

FAULT_ORDER = "ORD-456"


@tool(
    "get_customer",
    "Look up one customer by email address. Returns customer_id, name and "
    "loyalty tier. Use to verify identity before any order operation. Read only.",
    {"email": str},
)
async def get_customer(args: dict[str, Any]) -> dict[str, Any]:
    c = CUSTOMERS.get(args["email"].strip().lower())
    if c is None:
        return err("validation", False, "No customer with that email.")
    return ok(c)


@tool(
    "lookup_order",
    "Look up one order by its ID. Returns status, delivered_on, amount, sku, "
    "condition and charges (how many times the card was charged). Use for any "
    "question about the state of one specific order. Read only.",
    {"order_id": str},
)
async def _lookup_order_healthy(args: dict[str, Any]) -> dict[str, Any]:
    o = ORDERS.get(args["order_id"].strip().upper())
    if o is None:
        return err("validation", False, "Unknown order id.")
    return ok({"order_id": args["order_id"].strip().upper(), **o})


@tool(
    "read_policy",
    "Read one clause of the Northwind support policy by section number, e.g. "
    "'2.2'. Use when a decision depends on written policy. Read only. A section "
    "that does not exist returns found=false plus the list of sections that DO "
    "exist — a valid empty result, not an error, and not a reason to keep "
    "guessing section numbers.",
    {"section": str},
)
async def read_policy(args: dict[str, Any]) -> dict[str, Any]:
    section = args["section"].strip()
    text = POLICY.get(section)
    if text is not None:
        return ok({"section": section, "text": text, "found": True})
    # Deliberately NOT an error: the lookup ran and matched nothing. Return the
    # index so the caller stops probing. (Contrast lookup_order's timeout.)
    return ok({
        "section": section, "text": None, "found": False,
        "available_sections": sorted(POLICY),
    })


@tool(
    "process_refund",
    "Issue a refund of a given amount against one order. Mutating. Only call "
    "after the order has been looked up and the customer verified. Refunds over "
    "the automatic ceiling are denied before this runs — do not retry a denied "
    "refund, escalate it.",
    {"order_id": str, "amount": float},
)
async def process_refund(args: dict[str, Any]) -> dict[str, Any]:
    entry = {"order_id": args["order_id"].strip().upper(), "amount": float(args["amount"])}
    # idempotent: a repeated identical refund returns the first result, no double charge
    if entry not in REFUND_LOG:
        REFUND_LOG.append(entry)
    return ok({"ok": True, "refunded": entry["amount"], "order_id": entry["order_id"]})


@tool(
    "escalate_to_human",
    "Hand the case to a human agent. Supply customer_id, root_cause and "
    "recommended_action, because the human cannot see this conversation or any "
    "subagent's findings.",
    {"customer_id": str, "root_cause": str, "recommended_action": str},
)
async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
    return ok({
        "ok": True,
        "ticket": "ESC-9001",
        "customer_id": args["customer_id"],
        "root_cause": args["root_cause"],
        "recommended_action": args["recommended_action"],
    })


def _lookup_order_bare():
    @tool("lookup_order", _lookup_order_healthy.description, {"order_id": str})
    async def fn(args: dict[str, Any]) -> dict[str, Any]:
        if args["order_id"].strip().upper() == FAULT_ORDER:
            return {"content": [{"type": "text", "text": "Lookup failed."}], "is_error": True}
        return await _lookup_order_healthy.handler(args)

    return fn


def _lookup_order_structured():
    @tool("lookup_order", _lookup_order_healthy.description, {"order_id": str})
    async def fn(args: dict[str, Any]) -> dict[str, Any]:
        if args["order_id"].strip().upper() == FAULT_ORDER:
            return err(
                "transient", True, "Order service timed out.",
                attempted=f"lookup_order({FAULT_ORDER})",
                partialResults=[
                    {"concern_id": "c2", "claim": f"{FAULT_ORDER} exists on this account.",
                     "evidence": "order id resolved before the timeout", "source": "order index"}
                ],
                alternatives=[
                    "retry lookup_order once",
                    "proceed with the other concerns and flag c2 as unresolved",
                    "escalate c2 to the billing team with what is known",
                ],
            )
        return await _lookup_order_healthy.handler(args)

    return fn


_CATALOGUE_ORDER = ["get_customer", "lookup_order", "read_policy",
                    "process_refund", "escalate_to_human"]


def northwind_tool_names(only: list[str] | None = None) -> list[str]:
    return list(only) if only is not None else list(_CATALOGUE_ORDER)


def create_northwind(fault: str | None = None, only: list[str] | None = None):
    """Build the northwind MCP server.

    ``fault``: None | 'bare' | 'structured' — how lookup_order behaves for ORD-456.
    ``only``: short tool names to include. This is the hard tool boundary for a
    scoped specialist — ``ClaudeAgentOptions(tools=...)`` only narrows visibility,
    so a specialist that must not reach ``process_refund`` gets a server that
    does not contain it.
    """
    lookup = {
        None: _lookup_order_healthy,
        "bare": _lookup_order_bare(),
        "structured": _lookup_order_structured(),
    }[fault]
    catalogue = {
        "get_customer": get_customer,
        "lookup_order": lookup,
        "read_policy": read_policy,
        "process_refund": process_refund,
        "escalate_to_human": escalate_to_human,
    }
    return create_sdk_mcp_server(
        name="northwind", version="1.0.0",
        tools=[catalogue[n] for n in northwind_tool_names(only)],
    )


ALL_TOOL_NAMES = [
    "mcp__northwind__get_customer",
    "mcp__northwind__lookup_order",
    "mcp__northwind__read_policy",
    "mcp__northwind__process_refund",
    "mcp__northwind__escalate_to_human",
]


def days_since(delivered_on: str, today: str) -> int:
    return (date.fromisoformat(today) - date.fromisoformat(delivered_on)).days
