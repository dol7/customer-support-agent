"""Live probe for get_customer vs lookup_order misrouting.

Sends a handful of deliberately ambiguous first messages and reports which tool
the model reaches for first. Expectation: an identity-shaped ask -> get_customer;
an order-number-shaped ask (once identity exists) -> lookup_order; an
order-number-only ask with no identity -> get_customer (ask for id first) or a
plain-text request for identification.

    python scripts/routing_eval.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_agent.system_prompt import SYSTEM  # noqa: E402
from support_agent.tools import TOOL_DEFS  # noqa: E402

PROBES = [
    ("who am I on file as? email alice.nguyen@example.com, Alice Nguyen", None, "get_customer"),
    ("is my account in good standing? Bob Carter, bob.carter@example.com", None, "get_customer"),
    ("what's in ORD-123?", "CUST-1001", "lookup_order"),
    ("has ORD-789 shipped yet?", "CUST-1001", "lookup_order"),
    ("check ORD-456 for me", None, "get_customer|none"),  # no identity yet
    ("I'm Alice Nguyen (alice.nguyen@example.com), status of ORD-789?", None, "get_customer"),
]


def first_tool(client, message: str, verified: str | None) -> str:
    messages: list[dict] = []
    if verified:
        # simulate a session that already ran get_customer
        messages += [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": f"Thanks, I've verified your identity (customer {verified}). "
                f"How can I help?",
            },
        ]
    messages.append({"role": "user", "content": message})
    resp = client.messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
        max_tokens=1024,
        system=SYSTEM,
        tools=TOOL_DEFS,
        messages=messages,
        thinking={"type": "adaptive"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.name
    return "none"


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("set ANTHROPIC_API_KEY to run the routing eval", file=sys.stderr)
        return 2

    import anthropic

    client = anthropic.Anthropic()
    hits = 0
    for message, verified, expected in PROBES:
        got = first_tool(client, message, verified)
        ok = got in expected.split("|")
        hits += ok
        print(f"[{'ok ' if ok else 'MISS'}] expect {expected:<18} got {got:<16} | {message}")
    print(f"\n{hits}/{len(PROBES)} routed as expected")
    return 0 if hits == len(PROBES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
