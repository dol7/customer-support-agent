"""One PreToolUse hook enforcing the refund ceiling for every agent.

Registered once, against ``mcp__northwind__process_refund``. It fires whether
the caller is the coordinator or any subagent — the SDK runs PreToolUse hooks
for subagent tool calls too — so the $500 rule is enforced in exactly one place
instead of being copied into four subagent prompts (where copies drift and can
be argued past).

A ``deny`` decision comes back to the calling agent as a tool error. The agent
is expected to treat that as data: not retry, and escalate instead.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import HookMatcher

from .config import REFUND_CEILING

# Records every decision for the transcript: which agent, how much, allowed/denied.
DECISIONS: list[dict] = []

# The host sets this to the specialist label before each run_agent() call, since
# host-run specialists are plain queries and carry no agent_type of their own.
CURRENT_AGENT: str = "coordinator"


async def enforce_ceiling(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    amount = float(input_data.get("tool_input", {}).get("amount") or 0)
    agent = input_data.get("agent_type") or CURRENT_AGENT
    order_id = input_data.get("tool_input", {}).get("order_id")

    if amount <= REFUND_CEILING:
        DECISIONS.append({"agent": agent, "order_id": order_id, "amount": amount, "decision": "allow"})
        return {}

    DECISIONS.append({"agent": agent, "order_id": order_id, "amount": amount, "decision": "deny"})
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"${amount:.2f} is over the ${REFUND_CEILING:.2f} automatic "
                "refund ceiling (policy 3.5). This refund needs Tier 2 approval "
                "— escalate to a human agent instead of retrying."
            ),
        }
    }


# --- coordinator scope -------------------------------------------------------------
# ClaudeAgentOptions(tools=...) narrows *visibility* but does not hard-restrict:
# the coordinator was observed calling lookup_order anyway. This hook makes the
# coordinator's own tool surface real — it may only verify identity; every other
# northwind tool belongs to a specialist. Subagent calls (agent_type set) pass
# through untouched; their AgentDefinition.tools already scopes them.
COORDINATOR_ALLOWED = {"mcp__northwind__get_customer"}


async def scope_coordinator(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    if input_data.get("agent_type"):  # a subagent — not our concern here
        return {}
    name = input_data.get("tool_name", "")
    if name.startswith("mcp__northwind__") and name not in COORDINATOR_ALLOWED:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"The coordinator may not call {name} directly. Delegate this "
                    "to the specialist that owns it and pass the facts in its prompt."
                ),
            }
        }
    return {}


# The ceiling rule alone — for the single-agent baseline, which has no
# specialists to delegate to and so is not subject to coordinator scoping.
CEILING_HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="mcp__northwind__process_refund", hooks=[enforce_ceiling]),
    ]
}

# The full set the coordinator runs with: the ceiling (every agent) + coordinator
# scoping (coordinator may only verify identity).
HOOKS = {
    "PreToolUse": [
        HookMatcher(matcher="mcp__northwind__process_refund", hooks=[enforce_ceiling]),
        HookMatcher(matcher="mcp__northwind__*", hooks=[scope_coordinator]),
    ]
}


def reset() -> None:
    DECISIONS.clear()
