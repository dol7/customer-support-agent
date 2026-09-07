"""Least privilege: every specialist names its tools explicitly."""

from coordinator.agents import AGENTS, COORDINATOR_TOOLS, LOOSE_AGENTS

EXPECTED = {
    "order-investigator": ["mcp__northwind__lookup_order"],
    "policy-analyst": ["mcp__northwind__read_policy"],
    "refund-processor": ["mcp__northwind__process_refund"],
    "escalation-writer": ["mcp__northwind__escalate_to_human"],
}


def test_four_specialists():
    assert set(AGENTS) == set(EXPECTED)


def test_each_specialist_has_an_explicit_single_tool():
    for name, agent in AGENTS.items():
        assert agent.tools is not None, f"{name} left tools unset — would inherit everything"
        assert agent.tools == EXPECTED[name], name


def _holders(tool: str) -> list[str]:
    return [n for n, a in AGENTS.items() if any(tool in t for t in (a.tools or []))]


def test_only_refund_processor_can_move_money():
    assert _holders("process_refund") == ["refund-processor"]


def test_only_escalation_writer_can_open_a_ticket():
    assert _holders("escalate_to_human") == ["escalation-writer"]


def test_coordinator_holds_only_identity_verification():
    assert "mcp__northwind__get_customer" in COORDINATOR_TOOLS
    assert not any(
        t.startswith("mcp__northwind__") and t != "mcp__northwind__get_customer"
        for t in COORDINATOR_TOOLS
    )


def test_loose_agents_is_the_documented_counter_example():
    # tools omitted on purpose — this is what NOT to do
    assert LOOSE_AGENTS["order-investigator"].tools is None
