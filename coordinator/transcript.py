"""Records the run event stream to a readable .md and a raw .json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRANSCRIPTS = Path(__file__).resolve().parent / "transcripts"


class Recorder:
    def __init__(self, title: str) -> None:
        self.title = title
        self.events: list[dict] = []

    def __call__(self, kind: str, data: dict) -> None:
        d = _plain(data)
        if kind in ("text", "tool_result") and self.events:
            prev = self.events[-1]
            if prev["kind"] == kind and _key(prev["data"]) == _key(d):
                return
        self.events.append({"kind": kind, "data": d})

    def note(self, text: str) -> None:
        self.events.append({"kind": "note", "data": {"text": text}})

    def raw(self, text: str) -> None:
        self.events.append({"kind": "raw", "data": {"text": text}})

    def to_markdown(self) -> str:
        out: list[str] = [f"# {self.title}", ""]
        for ev in self.events:
            k, d = ev["kind"], ev["data"]
            if k == "note":
                out += ["", f"> **{d['text']}**", ""]
            elif k == "raw":
                out += ["", d["text"], ""]
            elif k == "prompt":
                out += [f"### → {d['label']}", "", "```", d["text"].strip(), "```", ""]
            elif k == "tool_use":
                out += [f"`tool` **{d['name']}** — `{json.dumps(d['input'])}`", ""]
            elif k == "tool_result":
                flag = "  ⚠️ is_error" if d.get("is_error") else ""
                out += [f"`result`{flag}", "", "```", d["content"].strip(), "```", ""]
            elif k == "thinking":
                out += ["<details><summary>thinking</summary>", "", d["text"].strip(), "", "</details>", ""]
            elif k == "text":
                out += [d["text"].strip(), ""]
            elif k == "result":
                out += ["", f"_({d['label']} — {d['subtype']}; running total "
                        f"{d['usage']['total_tokens']} tok, ${d['usage']['cost_usd']})_", ""]
        return "\n".join(out).rstrip() + "\n"

    def write(self, stem: str) -> Path:
        TRANSCRIPTS.mkdir(exist_ok=True)
        base = TRANSCRIPTS / stem
        base.with_suffix(".md").write_text(self.to_markdown())
        base.with_suffix(".json").write_text(
            json.dumps({"title": self.title, "events": self.events}, indent=2) + "\n")
        return base.with_suffix(".md")


def _key(d: dict) -> str:
    return d.get("content", d.get("text", ""))


def _plain(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
