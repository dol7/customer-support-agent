"""Parse and check the subagent finding contract.

A finding is ``{concern_id, claim, evidence, source}``. The coverage check
compares the set of ``concern_id`` values in the findings against the ticket's
concern ids — that is the only reason the contract carries a concern_id.
"""

from __future__ import annotations

import json
import re
from typing import Any

REQUIRED = ("concern_id", "claim", "evidence", "source")


def extract_findings(blob: str) -> list[dict[str, Any]]:
    """Pull the last JSON array out of an agent's text and keep the elements
    that look like findings. Tolerant on purpose — the coordinator's prose
    around the array varies."""
    out: list[dict] = []
    for match in re.finditer(r"\[.*?\]", blob, re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            for el in parsed:
                if isinstance(el, dict) and "concern_id" in el and "claim" in el:
                    out.append(el)
    return out


def is_attributable(finding: dict) -> bool:
    return all(finding.get(k) not in (None, "") for k in REQUIRED)


def coverage_gaps(concerns: list[dict], findings: list[dict]) -> list[dict]:
    covered = {f.get("concern_id") for f in findings}
    return [c for c in concerns if c["id"] not in covered]
