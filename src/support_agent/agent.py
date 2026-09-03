"""The hand-written agentic loop.

Control flow is driven entirely by ``response.stop_reason``:

* ``tool_use``   -> run every tool_use block, append one user message with all the
                    tool_result blocks (each carrying its matching tool_use_id),
                    continue.
* ``end_turn``   -> done. This is the primary and normal way the loop ends.
* ``max_tokens`` -> raise. The turn is truncated and unusable.
* anything else  -> raise ``UnexpectedStopReason`` (we do not guess).

The iteration counter is a *safety net*, not the termination mechanism: a healthy
conversation returns on ``end_turn`` long before it trips.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .backend import Backend, SessionContext, new_backend
from .errors import LoopSafetyCapExceeded, MaxTokensError, UnexpectedStopReason
from .system_prompt import SYSTEM
from .tools import TOOL_DEFS, FailMode, dispatch

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_ITERATIONS = 10  # safety net only
_MAX_TOKENS = 4096


@dataclass
class ToolCall:
    name: str
    input: dict
    result: dict


@dataclass
class Result:
    reply: str
    messages: list[dict]
    tool_calls: list[ToolCall] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str | None = None
    tickets: list[dict] = field(default_factory=list)


def run_conversation(
    client: Any,
    user_message: str,
    *,
    ctx: SessionContext | None = None,
    backend: Backend | None = None,
    fail_mode: FailMode | str | None = None,
    model: str = DEFAULT_MODEL,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    on_event: Any = None,
) -> Result:
    """Run one customer message to a final reply.

    ``client`` only needs a ``messages.create(...)`` returning an object with
    ``.stop_reason`` and ``.content`` (a list of blocks). The real
    ``anthropic.Anthropic()`` satisfies this; so does the test fake.
    """
    ctx = ctx or SessionContext()
    backend = backend or new_backend()
    if not isinstance(fail_mode, FailMode):
        fail_mode = FailMode(fail_mode or "none")

    messages: list[dict] = [{"role": "user", "content": user_message}]
    tool_calls: list[ToolCall] = []
    iterations = 0

    _emit(on_event, "user_message", {"text": user_message})

    while True:
        # --- safety net: NOT the primary exit --------------------------------------
        if iterations >= max_iterations:
            raise LoopSafetyCapExceeded(
                f"safety net tripped after {iterations} iterations without an end_turn; "
                f"the model is stuck in a tool-calling cycle"
            )
        iterations += 1

        response = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM,
            tools=TOOL_DEFS,
            messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
        )
        stop_reason = getattr(response, "stop_reason", None)
        _emit(on_event, "assistant_turn", {"stop_reason": stop_reason, "content": response.content})

        # --- max_tokens: raise ----------------------------------------------------
        if stop_reason == "max_tokens":
            raise MaxTokensError(
                "response stopped on max_tokens; increase max_tokens or split the request"
            )

        # --- end_turn: the primary termination ----------------------------------
        if stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            return Result(
                reply=_text_of(response.content),
                messages=messages,
                tool_calls=tool_calls,
                iterations=iterations,
                stop_reason=stop_reason,
                tickets=list(ctx.tickets),
            )

        # --- tool_use: run every block, append results, continue --------------
        if stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_result_blocks: list[dict] = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                payload = dispatch(
                    block.name,
                    dict(block.input),
                    ctx=ctx,
                    backend=backend,
                    fail_mode=fail_mode,
                )
                tool_calls.append(ToolCall(block.name, dict(block.input), payload))
                _emit(on_event, "tool_result", {"name": block.name, "input": block.input, "result": payload})
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,  # must match the tool_use block
                        "content": json.dumps(payload, separators=(",", ":")),
                    }
                )
            # one user message carrying ALL results, even if there were several
            messages.append({"role": "user", "content": tool_result_blocks})
            continue

        # --- anything else: do not guess ---------------------------------------
        raise UnexpectedStopReason(stop_reason)


def _text_of(content: list) -> str:
    parts = [b.text for b in content if getattr(b, "type", None) == "text"]
    return "\n".join(p for p in parts if p).strip()


def _emit(on_event: Any, kind: str, data: dict) -> None:
    if on_event is not None:
        on_event(kind, data)
