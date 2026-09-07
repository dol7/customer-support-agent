"""Shared configuration for the coordinator.

Auth note: the repo's ``.env`` holds an *identity-linked* ``ANTHROPIC_API_KEY``
that needs an ``anthropic-workspace-id`` header the Agent SDK's ``claude``
subprocess does not forward. Unsetting it makes the SDK fall back to the Claude
Code login, which works. Importing this module does that.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

# Fall back to the Claude Code login instead of the workspaceless API key.
for _var in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID"):
    os.environ.pop(_var, None)

# The Agent SDK injects the real system date into the model's context, so a
# frozen TODAY just makes the coordinator argue with it. Use the real date and
# keep the order dates at fixed offsets from it (see backend.py).
TODAY = date.today().isoformat()


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()

# The $500 rule. Mirrors support_agent.backend.REFUND_AUTO_APPROVAL_LIMIT from
# Week 1 — same number, now enforced by a hook instead of inside the tool.
try:
    from support_agent.backend import REFUND_AUTO_APPROVAL_LIMIT

    REFUND_CEILING = float(REFUND_AUTO_APPROVAL_LIMIT)
except Exception:  # noqa: BLE001 - keep the coordinator runnable standalone
    REFUND_CEILING = 500.00

# Sonnet everywhere by default — good enough for both roles and much cheaper
# than the SDK's default. Override per env if needed.
MODEL = os.environ.get("COORDINATOR_MODEL", "claude-sonnet-4-6")
SPECIALIST_MODEL = os.environ.get("COORDINATOR_SPECIALIST_MODEL", MODEL)
COORDINATOR_MODEL = MODEL

MAX_COVERAGE_ROUNDS = 3
