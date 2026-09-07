"""One PreToolUse hook, enforced once for every agent."""

import asyncio

from coordinator import hook
from coordinator.config import REFUND_CEILING
from coordinator.hook import CEILING_HOOKS, HOOKS, enforce_ceiling, scope_coordinator


def _call(amount, agent_type=None):
    hook.reset()
    inp = {
        "tool_name": "mcp__northwind__process_refund",
        "tool_input": {"order_id": "ORD-1", "amount": amount},
        "hook_event_name": "PreToolUse",
        "agent_type": agent_type,
    }
    return asyncio.run(enforce_ceiling(inp, "tu_1", None))


def test_allows_at_or_below_ceiling():
    assert _call(REFUND_CEILING) == {}
    assert _call(1.00) == {}
    assert hook.DECISIONS[-1]["decision"] == "allow"


def test_denies_above_ceiling_with_the_documented_shape():
    out = _call(REFUND_CEILING + 0.01)
    hs = out["hookSpecificOutput"]
    assert hs["hookEventName"] == "PreToolUse"
    assert hs["permissionDecision"] == "deny"
    assert "escalate" in hs["permissionDecisionReason"].lower()
    assert "3.5" in hs["permissionDecisionReason"]


def test_fires_for_subagents_too_and_records_which_agent():
    _call(9999.0, agent_type="refund-processor")
    assert hook.DECISIONS[-1] == {
        "agent": "refund-processor", "order_id": "ORD-1", "amount": 9999.0, "decision": "deny",
    }
    _call(9999.0, agent_type=None)  # coordinator's own call
    assert hook.DECISIONS[-1]["agent"] == "coordinator"


def test_missing_amount_is_safe():
    hook.reset()
    inp = {"tool_name": "mcp__northwind__process_refund", "tool_input": {}, "hook_event_name": "PreToolUse"}
    assert asyncio.run(enforce_ceiling(inp, None, None)) == {}


def test_the_ceiling_is_one_hook_against_the_refund_tool():
    # exactly one matcher enforces the ceiling, and it targets process_refund
    ceiling_matchers = [
        m for m in HOOKS["PreToolUse"] if enforce_ceiling in m.hooks
    ]
    assert len(ceiling_matchers) == 1
    assert ceiling_matchers[0].matcher == "mcp__northwind__process_refund"
    # and it stands alone in the baseline hook set
    assert CEILING_HOOKS["PreToolUse"][0].hooks == [enforce_ceiling]


def test_scope_coordinator_is_a_separate_rule_not_a_second_ceiling():
    scope_matchers = [m for m in HOOKS["PreToolUse"] if scope_coordinator in m.hooks]
    assert len(scope_matchers) == 1
    assert scope_matchers[0].matcher == "mcp__northwind__*"
