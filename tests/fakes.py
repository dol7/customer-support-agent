"""A scripted stand-in for ``anthropic.Anthropic`` — no network.

Build the exact turns you want the "model" to take and assert on the loop's
behaviour deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ThinkingBlock:
    thinking: str
    type: str = "thinking"


@dataclass
class ToolUseBlock:
    name: str
    input: dict
    id: str
    type: str = "tool_use"


@dataclass
class FakeMessage:
    stop_reason: str
    content: list
    role: str = "assistant"


@dataclass
class _Messages:
    parent: "FakeAnthropic"

    def create(self, **kwargs: Any) -> FakeMessage:
        self.parent.calls.append(kwargs)
        if not self.parent.scripted:
            raise AssertionError("FakeAnthropic ran out of scripted responses")
        nxt = self.parent.scripted.pop(0)
        return nxt(kwargs) if callable(nxt) else nxt


@dataclass
class FakeAnthropic:
    scripted: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.messages = _Messages(self)


def tool_use_turn(*calls: tuple[str, dict]) -> FakeMessage:
    blocks = [
        ToolUseBlock(name=name, input=inp, id=f"toolu_{i}") for i, (name, inp) in enumerate(calls)
    ]
    return FakeMessage(stop_reason="tool_use", content=blocks)


def final_turn(text: str) -> FakeMessage:
    return FakeMessage(stop_reason="end_turn", content=[TextBlock(text=text)])
