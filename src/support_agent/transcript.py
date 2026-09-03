"""Turn-by-turn recorder. Produces a human-readable ``.md`` and a raw ``.json``.

Wire it in via ``run_conversation(..., on_event=recorder)``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TranscriptRecorder:
    def __init__(self, title: str) -> None:
        self.title = title
        self.events: list[dict] = []

    def __call__(self, kind: str, data: dict) -> None:
        self.events.append({"kind": kind, "data": _plain(data)})

    # --- rendering -----------------------------------------------------------------
    def to_markdown(self) -> str:
        lines: list[str] = [f"# {self.title}", ""]
        for ev in self.events:
            kind, data = ev["kind"], ev["data"]
            if kind == "user_message":
                lines += ["## Customer", "", "> " + data["text"].replace("\n", "\n> "), ""]
            elif kind == "assistant_turn":
                lines += [f"## Assistant turn — stop_reason: `{data['stop_reason']}`", ""]
                for block in data["content"]:
                    btype = block.get("type")
                    if btype == "thinking" and block.get("thinking"):
                        lines += ["<details><summary>thinking (summarized)</summary>", "",
                                  block["thinking"], "", "</details>", ""]
                    elif btype == "text" and block.get("text"):
                        lines += [block["text"], ""]
                    elif btype == "tool_use":
                        lines += [
                            f"**tool_use** `{block.get('name')}`  (id `{block.get('id')}`)",
                            "",
                            "```json",
                            json.dumps(block.get("input", {}), indent=2),
                            "```",
                            "",
                        ]
            elif kind == "tool_result":
                lines += [
                    f"### tool_result — `{data['name']}`",
                    "",
                    "```json",
                    json.dumps(data["result"], indent=2),
                    "```",
                    "",
                ]
        return "\n".join(lines).rstrip() + "\n"

    def to_json(self) -> str:
        return json.dumps({"title": self.title, "events": self.events}, indent=2) + "\n"

    def write(self, stem: Path | str) -> None:
        stem = Path(stem)
        stem.with_suffix(".md").write_text(self.to_markdown())
        stem.with_suffix(".json").write_text(self.to_json())


def _plain(obj: Any) -> Any:
    """Turn SDK content-block objects into plain JSON-able structures."""
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # SDK block object
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return _plain(fn())
            except Exception:  # noqa: BLE001
                pass
    if hasattr(obj, "__dict__"):
        return {k: _plain(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)
