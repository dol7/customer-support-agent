"""Guards on the tool descriptions — the overlapping pair especially.

We can't unit-test "the model routes correctly" (that needs the live model —
see scripts/routing_eval.py). We CAN test that every description carries the
structure that makes correct routing possible: purpose, input formats, outputs,
and explicit "when NOT to use" boundaries that point at the sibling tool."""

from support_agent.tools import TOOL_DEFS

BY_NAME = {t["name"]: t for t in TOOL_DEFS}


def test_all_four_tools_present_with_the_three_api_fields():
    assert set(BY_NAME) == {"get_customer", "lookup_order", "process_refund", "escalate_to_human"}
    for t in TOOL_DEFS:
        assert set(t) >= {"name", "description", "input_schema"}
        assert t["input_schema"]["additionalProperties"] is False


def test_every_description_states_purpose_inputs_outputs_and_boundaries():
    for name, t in BY_NAME.items():
        d = t["description"].lower()
        assert "output" in d, name
        assert "when not to use" in d, name
        # input formats are spelled out
        assert any(fmt in d for fmt in ("e.164", "rfc-5322", '"ord-', "decimal")), name


def test_overlapping_pair_cross_references_each_other():
    gc = BY_NAME["get_customer"]["description"].lower()
    lo = BY_NAME["lookup_order"]["description"].lower()
    # get_customer tells the model when to use lookup_order instead, and vice versa
    assert "lookup_order" in gc
    assert "get_customer" in lo
    # and each names its distinguishing key
    assert "order number" in gc  # get_customer: "cannot ... from an order number"
    assert "identity is already established" in lo or "already verified" in lo


def test_process_refund_tells_the_model_not_to_retry_a_permission_error():
    d = BY_NAME["process_refund"]["description"].lower()
    assert "do not retry" in d or "do not retry," in d
    assert "escalate_to_human" in d


def test_strict_schemas_have_all_properties_required():
    for t in TOOL_DEFS:
        schema = t["input_schema"]
        assert set(schema["required"]) == set(schema["properties"]), t["name"]
