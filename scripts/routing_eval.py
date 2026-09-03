"""Live probe for get_customer <-> lookup_order misrouting.

"Misrouting" means reaching for the *wrong sibling*: calling lookup_order for an
identity question, or calling get_customer for a question about a specific order.
That is what this eval checks. It also flags jumping straight to lookup_order for
an order the customer named before identity was established.

Each probe declares which first tools are acceptable and which would be a
misroute. `none` (the model answered/clarified in text) is not a misroute — it is
the model being conservative — but it is reported so drift is visible.

    python scripts/routing_eval.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_agent.system_prompt import SYSTEM  # noqa: E402
from support_agent.tools import TOOL_DEFS  # noqa: E402

# (message, verified_customer_id | None, ok_tools, misroute_tools)
PROBES = [
    ("who am I on file as? email alice.nguyen@example.com, Alice Nguyen",
     None, {"get_customer", "none"}, {"lookup_order", "process_refund"}),
    ("is my account in good standing? Bob Carter, bob.carter@example.com",
     None, {"get_customer", "none"}, {"lookup_order", "process_refund"}),
    ("what's my email and phone on file? Alice Nguyen, alice.nguyen@example.com",
     None, {"get_customer", "none"}, {"lookup_order", "process_refund"}),
    ("show me the line items and total on ORD-123",
     "CUST-1001", {"lookup_order", "none"}, {"get_customer"}),
    ("has ORD-789 shipped yet?",
     "CUST-1001", {"lookup_order", "none"}, {"get_customer"}),
    ("can you refund ORD-123 for me? it's damaged",
     "CUST-1001", {"lookup_order", "process_refund", "none"}, {"get_customer"}),
    # order number only, identity NOT established -> jumping to lookup_order is the misroute
    ("check ORD-456 for me",
     None, {"get_customer", "none"}, {"lookup_order", "process_refund"}),
    ("I'm Alice Nguyen (alice.nguyen@example.com), what's the status of ORD-789?",
     None, {"get_customer", "none"}, {"lookup_order", "process_refund"}),
]


def _verified_history(customer_id: str, message: str) -> list[dict]:
    """A faithful already-verified session: a real get_customer tool_use +
    tool_result, then the probe message."""
    return [
        {"role": "user", "content": "hi, I need some help with my account"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Sure - let me pull up your account."},
                {
                    "type": "tool_use",
                    "id": "toolu_seed",
                    "name": "get_customer",
                    "input": {
                        "full_name": "Alice Nguyen",
                        "email": "alice.nguyen@example.com",
                        "phone": None,
                    },
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_seed",
                    "content": (
                        '{"ok":true,"customer_id":"%s","name":"Alice Nguyen",'
                        '"email":"alice.nguyen@example.com","verified":true,'
                        '"account_status":"active","open_order_count":1}' % customer_id
                    ),
                }
            ],
        },
        {"role": "assistant", "content": "You're verified. What can I help with?"},
        {"role": "user", "content": message},
    ]


def first_tool(client, message: str, verified: str | None) -> str:
    messages = (
        _verified_history(verified, message)
        if verified
        else [{"role": "user", "content": message}]
    )
    resp = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
        max_tokens=4096,
        system=SYSTEM,
        tools=TOOL_DEFS,
        messages=messages,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.name
    return "none(max_tokens)" if resp.stop_reason == "max_tokens" else "none"


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("set ANTHROPIC_API_KEY to run the routing eval", file=sys.stderr)
        return 2

    from support_agent.client import make_client

    client = make_client()
    misroutes = 0
    for message, verified, ok_tools, misroute_tools in PROBES:
        got = first_tool(client, message, verified)
        base = got.split("(")[0]
        if base in misroute_tools:
            tag, misroutes = "MISROUTE", misroutes + 1
        elif base in ok_tools:
            tag = "ok      "
        else:
            tag = "unclear "
        print(f"[{tag}] got {got:<18} | {message}")
    print(f"\n{misroutes} misroute(s) across {len(PROBES)} probes "
          f"(a misroute = the wrong sibling tool)")
    return 1 if misroutes else 0


if __name__ == "__main__":
    raise SystemExit(main())
