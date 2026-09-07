"""The four specialist subagents, plus the deliberately-wrong counter-example.

Least privilege: each ``AgentDefinition`` names exactly the one tool its role
needs and nothing else. None of these assignments is arbitrary —

* order-investigator  -> lookup_order   (reads order state; never mutates)
* policy-analyst      -> read_policy     (reads written policy; no order access)
* refund-processor    -> process_refund  (the only agent that moves money)
* escalation-writer   -> escalate_to_human (the only agent that opens a ticket)

``get_customer`` is held by the coordinator, not any specialist: identity
verification is a coordinator responsibility and its result is a fact the
coordinator passes down.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from .config import SPECIALIST_MODEL
from .prompts import FINDING_CONTRACT

AGENTS: dict[str, AgentDefinition] = {
    "order-investigator": AgentDefinition(
        description="Looks up the status, dates, amount, condition and charge "
                    "count of ONE order named in the prompt. Use for any "
                    "question about the state of a specific order.",
        prompt="You investigate one order. Call lookup_order once for the order "
               "id in your prompt, then answer from the fields it returns "
               "(status, delivered_on, amount, sku, condition, charges). Do not "
               "retry a failed lookup — report the failure instead."
               + FINDING_CONTRACT,
        tools=["mcp__northwind__lookup_order"],
        model=SPECIALIST_MODEL,
        maxTurns=4,
        background=False,
    ),
    "policy-analyst": AgentDefinition(
        description="Answers a question that depends on written Northwind "
                    "policy — return windows, escalation triggers — given the "
                    "facts in the prompt. Has no access to orders or a clock.",
        prompt="You answer one policy question. Every fact you need (sku, "
               "delivered_on date, today's date, what the customer said) is in "
               "your prompt — you cannot look any of it up. Read the relevant "
               "policy section(s) with read_policy. If read_policy returns "
               "found=false it also returns available_sections — trust that "
               "list, do not keep guessing section numbers. Cite the section "
               "number you used, then answer." + FINDING_CONTRACT,
        tools=["mcp__northwind__read_policy"],
        model=SPECIALIST_MODEL,
        maxTurns=5,
        background=False,
    ),
    "refund-processor": AgentDefinition(
        description="Issues ONE refund against an order that has already been "
                    "investigated and a customer already verified. Use only to "
                    "execute a refund the coordinator has decided on.",
        prompt="You issue exactly the one refund named in your prompt: call "
               "process_refund with the order id and amount given. If the "
               "refund is denied, do not retry — report the denial as your "
               "finding so the coordinator can escalate." + FINDING_CONTRACT,
        tools=["mcp__northwind__process_refund"],
        model=SPECIALIST_MODEL,
        maxTurns=4,
        background=False,
    ),
    "escalation-writer": AgentDefinition(
        description="Compiles a structured handoff for a human agent. Use when "
                    "policy requires a human, or the automated system cannot "
                    "act on a concern.",
        prompt="You write one escalation handoff. Call escalate_to_human with "
               "customer_id, root_cause and recommended_action — all three from "
               "your prompt, because the human cannot see this conversation or "
               "any subagent's findings." + FINDING_CONTRACT,
        tools=["mcp__northwind__escalate_to_human"],
        model=SPECIALIST_MODEL,
        maxTurns=4,
        background=False,
    ),
}

# The counter-example for the tool-scoping demo. `tools` is omitted, so this
# agent silently inherits every tool in the session — including process_refund,
# which its own prompt forbids it to use. Demo `scoping` shows it refunding
# anyway; the scoped AGENTS["order-investigator"] above does not.
LOOSE_AGENTS: dict[str, AgentDefinition] = {
    "order-investigator": AgentDefinition(
        description="Looks up order status, dates and amounts.",
        prompt="You investigate orders. You never issue refunds." + FINDING_CONTRACT,
        model=SPECIALIST_MODEL,
        maxTurns=4,
        # tools omitted on purpose
    ),
}

# Coordinator's own tool surface: spawn subagents + verify identity. Nothing else.
COORDINATOR_TOOLS = ["Agent", "mcp__northwind__get_customer"]
