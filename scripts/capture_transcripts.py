"""Run the demo scenarios against the real Anthropic API and write transcripts/.

    python scripts/capture_transcripts.py            # all scenarios
    python scripts/capture_transcripts.py happy      # just one

Needs ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN). Model from ANTHROPIC_MODEL,
default claude-opus-5.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from support_agent.agent import run_conversation  # noqa: E402
from support_agent.backend import SessionContext, new_backend  # noqa: E402
from support_agent.transcript import TranscriptRecorder  # noqa: E402

OUT = ROOT / "transcripts"

SCENARIOS: dict[str, dict] = {
    "happy_path_alice": {
        "title": "Happy path — Alice Nguyen — two jobs in one message",
        "message": (
            "Hi, this is Alice Nguyen (alice.nguyen@example.com). Two things: the blender "
            "from ORD-123 turned up with a cracked jug, so I'd like a refund for it; and "
            "separately, can you tell me where ORD-789 is right now?"
        ),
        "fail_mode": "none",
    },
    "escalation_bob": {
        "title": "Escalation — Bob Carter explicitly asks for a human (ORD-456)",
        "message": (
            "This is Bob Carter, bob.carter@example.com. I've gone back and forth on ORD-456 "
            "too many times already. I don't want to go through it again with a bot — please "
            "put me through to a real person."
        ),
        "fail_mode": "none",
    },
    "over_limit_demo": {
        "title": "Enforcement + escalation — Bob wants a $742 refund (above the code ceiling)",
        "message": (
            "Bob Carter here (bob.carter@example.com). The standing desk frame from ORD-456 "
            "arrived bent in the box. I want the full amount back please."
        ),
        "fail_mode": "none",
    },
    "errors_transient": {
        "title": "Transient error — the order service times out once, agent retries",
        "message": (
            "Hi, Alice Nguyen, alice.nguyen@example.com — can you check the status of ORD-789 "
            "for me?"
        ),
        "fail_mode": "transient",
    },
}


def run_one(key: str) -> None:
    spec = SCENARIOS[key]
    import anthropic

    client = anthropic.Anthropic()
    recorder = TranscriptRecorder(title=spec["title"])
    result = run_conversation(
        client,
        spec["message"],
        ctx=SessionContext(),
        backend=new_backend(),
        fail_mode=spec["fail_mode"],
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5"),
        on_event=recorder,
    )
    # append the final consolidated reply + a short machine summary
    recorder.events.append(
        {
            "kind": "assistant_turn",
            "data": {"stop_reason": "end_turn", "content": [{"type": "text", "text": result.reply}]},
        }
    )
    OUT.mkdir(exist_ok=True)
    recorder.write(OUT / key)
    tools = ", ".join(c.name for c in result.tool_calls) or "(none)"
    tickets = ", ".join(t["ticket_id"] for t in result.tickets) or "(none)"
    print(f"  {key}: {result.iterations} turns | tools: {tools} | tickets: {tickets}")


def main(argv: list[str]) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("set ANTHROPIC_API_KEY to capture transcripts", file=sys.stderr)
        return 2

    keys = argv or list(SCENARIOS)
    unknown = [k for k in keys if k not in SCENARIOS]
    if unknown:
        print(f"unknown scenario(s): {unknown}; pick from {list(SCENARIOS)}", file=sys.stderr)
        return 2
    print(f"capturing {len(keys)} scenario(s) to {OUT}/ ...")
    for k in keys:
        run_one(k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
