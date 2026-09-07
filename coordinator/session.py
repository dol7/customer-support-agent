"""Running agents on the Claude Agent SDK.

Two entry points:

* ``run_agent(agent, task, ...)`` — run ONE specialist (an ``AgentDefinition``)
  as its own scoped ``query()``. Its ``tools`` list becomes the session's
  ``allowed_tools``; it has no ``Agent`` tool, so it cannot sub-spawn and it
  finishes synchronously. This is how the coordinator delegates.
* ``run_plain(system, prompt, ...)`` — run the coordinator itself with no
  specialist tools, for decomposition and the final report.

Both accumulate token usage into a shared ``Metrics`` and stream events to an
optional recorder. Findings are pulled off the stream as they appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from . import hook as _hook
from .config import COORDINATOR_MODEL
from .findings import extract_findings
from .hook import CEILING_HOOKS
from .tools import ALL_TOOL_NAMES, create_northwind


@dataclass
class Metrics:
    runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, result: ResultMessage) -> None:
        self.runs += 1
        u = getattr(result, "usage", None) or {}
        self.input_tokens += int(u.get("input_tokens", 0))
        self.output_tokens += int(u.get("output_tokens", 0))
        self.cache_read_tokens += int(u.get("cache_read_input_tokens", 0))
        self.cache_creation_tokens += int(u.get("cache_creation_input_tokens", 0))
        self.cost_usd += float(getattr(result, "total_cost_usd", 0.0) or 0.0)

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens + self.output_tokens
                + self.cache_read_tokens + self.cache_creation_tokens)

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs, "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "total_tokens": self.total_tokens, "cost_usd": round(self.cost_usd, 4),
        }


@dataclass
class RunResult:
    text: str
    findings: list[dict] = field(default_factory=list)


def _options(*, system_prompt: str, allowed_tools: list[str], fault: str | None,
             hooks: dict | None, max_turns: int,
             server_tools: list[str] | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        # server_tools is the HARD boundary — the server only contains these.
        mcp_servers={"northwind": create_northwind(fault, only=server_tools)},
        model=COORDINATOR_MODEL,
        system_prompt=system_prompt,
        tools=allowed_tools,
        allowed_tools=allowed_tools,
        hooks=hooks,
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=max_turns,
    )


async def _drive(options: ClaudeAgentOptions, prompt: str, *, label: str,
                 metrics: Metrics, on_event: Callable | None) -> RunResult:
    text = ""
    findings: list[dict] = []
    seen: set = set()

    def collect(s: str) -> None:
        for f in extract_findings(s):
            key = (f.get("concern_id"), f.get("claim", "")[:80])
            if key not in seen:
                seen.add(key)
                findings.append(f)

    if on_event:
        on_event("prompt", {"label": label, "text": prompt})
    tool_names: dict[str, str] = {}

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ThinkingBlock) and block.thinking.strip():
                        if on_event:
                            on_event("thinking", {"label": label, "text": _clip(block.thinking)})
                    elif isinstance(block, TextBlock) and block.text.strip():
                        txt = block.text.strip()
                        text = txt
                        collect(txt)
                        if on_event:
                            on_event("text", {"label": label, "text": _clip(txt)})
                    elif isinstance(block, ToolUseBlock):
                        tool_names[block.id] = block.name
                        if on_event:
                            on_event("tool_use", {"label": label, "name": block.name, "input": block.input})
            elif isinstance(message, UserMessage):
                for block in _as_list(message.content):
                    if isinstance(block, ToolResultBlock):
                        content = _text_of(block.content)
                        collect(content)
                        if on_event:
                            on_event("tool_result", {
                                "label": label, "content": _clip(content),
                                "is_error": bool(getattr(block, "is_error", False)),
                            })
            elif isinstance(message, ResultMessage):
                metrics.add(message)
                if message.result:
                    text = message.result
                    collect(message.result)
                if on_event:
                    on_event("result", {"label": label, "subtype": message.subtype,
                                        "usage": metrics.as_dict()})
    except ClaudeSDKError as exc:
        msg = f"{type(exc).__name__}: {exc}"
        if on_event:
            on_event("note", {"text": f"[{label}] run error — {msg}"})
        if not text:
            text = f"(run ended: {msg})"

    return RunResult(text=text, findings=findings)


async def run_agent(
    agent: AgentDefinition,
    task: str,
    *,
    metrics: Metrics,
    fault: str | None = None,
    on_event: Callable | None = None,
    label: str = "specialist",
    allowed_tools_override: list[str] | None = None,
) -> RunResult:
    """Run one specialist. Its own ``tools`` list is the allowlist unless
    overridden (the loose-agent demo overrides with the full server so an
    unscoped agent can reach every tool)."""
    if allowed_tools_override is not None:
        tools, server_tools = allowed_tools_override, None
    elif agent.tools is None:
        # tools field omitted -> the whole session; server carries every tool
        tools, server_tools = list(ALL_TOOL_NAMES), None
    else:
        # scoped -> the server only mounts this agent's tool(s)
        tools = agent.tools
        server_tools = [t.rsplit("__", 1)[-1] for t in agent.tools]
    opts = _options(system_prompt=agent.prompt, allowed_tools=tools, server_tools=server_tools,
                    fault=fault, hooks=CEILING_HOOKS, max_turns=(agent.maxTurns or 6) + 4)
    _hook.CURRENT_AGENT = label.split("/")[-1] or "specialist"
    try:
        return await _drive(opts, task, label=label, metrics=metrics, on_event=on_event)
    finally:
        _hook.CURRENT_AGENT = "coordinator"


async def run_plain(
    system: str,
    prompt: str,
    *,
    metrics: Metrics,
    on_event: Callable | None = None,
    label: str = "coordinator",
) -> RunResult:
    """Run the coordinator itself — decomposition or report. No specialist tools."""
    opts = _options(system_prompt=system, allowed_tools=[], fault=None,
                    hooks=None, max_turns=8)
    return await _drive(opts, prompt, label=label, metrics=metrics, on_event=on_event)


# --- helpers ------------------------------------------------------------------------
def _as_list(x: Any) -> list:
    return x if isinstance(x, list) else [x]


def _clip(text: str, limit: int = 900) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"\n… (+{len(text) - limit} chars)"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b["text"])
            elif getattr(b, "text", None):
                parts.append(b.text)
        return "".join(parts)
    return json.dumps(content, default=str)
