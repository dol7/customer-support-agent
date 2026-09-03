"""CLI: run one customer message through the agent.

    python -m support_agent "I need a refund for ORD-123 and the status of ORD-456"
    python -m support_agent --fail-mode business "refund ORD-456"
    python -m support_agent --json "..."     # dump the full event stream
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .agent import DEFAULT_MAX_ITERATIONS, DEFAULT_MODEL, run_conversation
from .errors import LoopError
from .tools import FailMode
from .transcript import TranscriptRecorder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="support_agent")
    parser.add_argument("message", help="the customer's message")
    parser.add_argument(
        "--fail-mode",
        default=os.environ.get("SUPPORT_AGENT_FAIL_MODE", "none"),
        choices=FailMode.VALID,
        help="inject one deterministic tool failure (default: none)",
    )
    parser.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=int(os.environ.get("SUPPORT_AGENT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)),
    )
    parser.add_argument("--json", action="store_true", help="print the raw event stream as JSON")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("set ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) to run against the API", file=sys.stderr)
        return 2

    try:
        from .client import make_client

        client = make_client()
    except ImportError:
        print("anthropic SDK not installed: pip install -r requirements.txt", file=sys.stderr)
        return 2
    recorder = TranscriptRecorder(title="CLI run")

    try:
        result = run_conversation(
            client,
            args.message,
            fail_mode=args.fail_mode,
            model=args.model,
            max_iterations=args.max_iterations,
            on_event=recorder,
        )
    except LoopError as exc:
        print(f"loop error ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(recorder.events, indent=2, default=str))
        return 0

    for call in result.tool_calls:
        ok = call.result.get("ok")
        tag = "ok" if ok else f"{call.result.get('errorCategory')} error"
        print(f"  [tool] {call.name}({_short(call.input)}) -> {tag}")
    for ticket in result.tickets:
        print(f"  [ticket] {ticket['ticket_id']} ({ticket['category']})")
    print()
    print(result.reply)
    print()
    print(f"({result.iterations} iterations, stop_reason={result.stop_reason})")
    return 0


def _short(d: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in d.items())


if __name__ == "__main__":
    raise SystemExit(main())
