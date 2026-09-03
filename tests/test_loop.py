"""The loop: stop_reason control flow, every tool_use block executed, results
appended with matching ids, cap is a safety net (not the primary exit)."""

import json

import pytest
from fakes import FakeAnthropic, FakeMessage, TextBlock, final_turn, tool_use_turn

from support_agent.agent import run_conversation
from support_agent.backend import SessionContext, new_backend
from support_agent.errors import LoopSafetyCapExceeded, MaxTokensError, UnexpectedStopReason


def _run(scripted, **kw):
    return run_conversation(
        FakeAnthropic(scripted=list(scripted)),
        "hello",
        ctx=SessionContext(verified_customer_id="CUST-1001"),
        backend=new_backend(),
        **kw,
    )


def test_end_turn_is_the_primary_termination():
    result = _run([final_turn("all done")])
    assert result.reply == "all done"
    assert result.stop_reason == "end_turn"
    assert result.iterations == 1


def test_tool_use_then_end_turn_appends_results_with_matching_ids():
    client = FakeAnthropic(
        scripted=[
            tool_use_turn(("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"})),
            final_turn("here is your order"),
        ]
    )
    result = run_conversation(
        client,
        "status of ORD-123",
        ctx=SessionContext(verified_customer_id="CUST-1001"),
        backend=new_backend(),
    )
    # the user message that follows the assistant tool_use turn
    tool_result_msg = result.messages[2]
    assert tool_result_msg["role"] == "user"
    block = tool_result_msg["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "toolu_0"  # matches the ToolUseBlock id
    assert json.loads(block["content"])["ok"] is True


def test_every_tool_use_block_in_one_response_is_executed():
    client = FakeAnthropic(
        scripted=[
            tool_use_turn(
                ("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}),
                ("lookup_order", {"order_id": "ORD-789", "customer_id": "CUST-1001"}),
            ),
            final_turn("both orders covered"),
        ]
    )
    result = run_conversation(
        client,
        "status of ORD-123 and ORD-789",
        ctx=SessionContext(verified_customer_id="CUST-1001"),
        backend=new_backend(),
    )
    assert [c.name for c in result.tool_calls] == ["lookup_order", "lookup_order"]
    # both results returned in a SINGLE user message
    tool_result_msg = result.messages[2]
    assert len(tool_result_msg["content"]) == 2
    assert {b["tool_use_id"] for b in tool_result_msg["content"]} == {"toolu_0", "toolu_1"}


def test_max_tokens_raises():
    with pytest.raises(MaxTokensError):
        _run([FakeMessage(stop_reason="max_tokens", content=[TextBlock("truncated...")])])


def test_unexpected_stop_reason_raises():
    with pytest.raises(UnexpectedStopReason):
        _run([FakeMessage(stop_reason="refusal", content=[])])


def test_iteration_cap_is_a_safety_net_not_the_exit():
    # model never stops calling tools -> the net trips
    forever = [
        tool_use_turn(("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"}))
        for _ in range(50)
    ]
    with pytest.raises(LoopSafetyCapExceeded):
        _run(forever, max_iterations=4)


def test_cap_does_not_fire_on_a_normal_multi_tool_conversation():
    scripted = [
        tool_use_turn(("get_customer", {"full_name": "x", "email": "x@y.z", "phone": None})),
        tool_use_turn(("lookup_order", {"order_id": "ORD-123", "customer_id": "CUST-1001"})),
        final_turn("done"),
    ]
    result = _run(scripted, max_iterations=10)
    assert result.stop_reason == "end_turn"
    assert result.iterations == 3
