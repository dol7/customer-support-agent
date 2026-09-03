"""Structured tool errors and loop-level exceptions.

Two different failure channels, kept deliberately separate:

1. **Tool errors** are *data*. A tool that cannot do its job returns a plain dict
   ``{"ok": False, "errorCategory": ..., "isRetryable": ..., "message": ...}``. It
   never raises. Claude reads the dict on the next turn and decides what to do
   (retry, explain to the customer, or escalate).

2. **Loop errors** are *exceptions*. They signal that the protocol between us and
   the model broke — the response was truncated, the model stopped for a reason
   the loop does not know how to handle, or the loop ran away. These are bugs or
   operational problems, not things Claude should reason about, so they raise.
"""

from __future__ import annotations

from typing import Literal

ErrorCategory = Literal["transient", "validation", "business", "permission"]

# Categories that it is safe for the model to retry as-is. `transient` failures
# clear on their own; `validation` failures clear once the model fixes the
# argument it sent. `business` and `permission` are terminal — the answer will
# not change on a retry, so the model must explain or escalate instead.
_RETRYABLE: dict[str, bool] = {
    "transient": True,
    "validation": True,
    "business": False,
    "permission": False,
}


def tool_error(category: ErrorCategory, message: str) -> dict:
    """Build the structured error payload a tool returns instead of raising.

    `message` is customer-safe for `business` errors (it may be read aloud to the
    customer) and operator-facing but harmless for the others.
    """
    if category not in _RETRYABLE:
        raise ValueError(f"unknown error category: {category!r}")
    return {
        "ok": False,
        "errorCategory": category,
        "isRetryable": _RETRYABLE[category],
        "message": message,
    }


class LoopError(RuntimeError):
    """Base class for agentic-loop protocol failures."""


class MaxTokensError(LoopError):
    """The model hit `max_tokens` mid-response. The turn is unusable."""


class LoopSafetyCapExceeded(LoopError):
    """The iteration safety net tripped.

    This is a backstop, not the normal way the loop ends — a healthy
    conversation terminates on ``stop_reason == "end_turn"`` well before the cap.
    Hitting it means the model got stuck in a tool-calling cycle.
    """


class UnexpectedStopReason(LoopError):
    """The model stopped for a reason the loop does not handle (e.g. `refusal`)."""

    def __init__(self, stop_reason: str | None) -> None:
        super().__init__(f"unhandled stop_reason: {stop_reason!r}")
        self.stop_reason = stop_reason
