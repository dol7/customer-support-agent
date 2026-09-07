"""CLI.

    python -m coordinator                 # resolve the built-in four-concern ticket
    python -m coordinator "<ticket text>" # resolve a custom ticket
    python -m coordinator --demo <name>   # run one demonstration (writes a transcript)
    python -m coordinator --demo all      # run every demonstration
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import backend, hook
from .backend import ALICE_TICKET
from .config import TODAY
from .coordinator import resolve
from .demos import DEMOS
from .transcript import Recorder


async def _resolve_cli(ticket: str) -> int:
    backend.reset(); hook.reset()
    rec = Recorder("CLI resolve")
    res = await resolve(ticket, today=TODAY, on_event=rec)
    print("\n=== concerns ===", [c["id"] for c in res.concerns])
    print("=== covered  ===", sorted({f.get("concern_id") for f in res.findings}))
    print("=== gaps     ===", [g["id"] for g in res.gaps] or "none")
    print("=== refunds  ===", backend.REFUND_LOG)
    print("=== hook     ===", hook.DECISIONS)
    print("=== tokens   ===", res.metrics.as_dict())
    print("\n" + "=" * 60 + "\nREPORT\n" + "=" * 60 + "\n" + res.report)
    return 0 if not res.gaps else 1


async def _run_demos(name: str) -> int:
    names = list(DEMOS) if name == "all" else [name]
    for n in names:
        if n not in DEMOS:
            print(f"unknown demo {n!r}; pick from {list(DEMOS)} or 'all'", file=sys.stderr)
            return 2
        print(f"\n### demo: {n}")
        await DEMOS[n]()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="coordinator")
    p.add_argument("ticket", nargs="?", default=ALICE_TICKET)
    p.add_argument("--demo", help="run a demonstration instead of resolving a ticket")
    args = p.parse_args(argv)

    if args.demo:
        return asyncio.run(_run_demos(args.demo))
    return asyncio.run(_resolve_cli(args.ticket))


if __name__ == "__main__":
    raise SystemExit(main())
