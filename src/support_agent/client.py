"""Construct the Anthropic client.

Identity-linked API keys require an ``anthropic-workspace-id`` header. If
``ANTHROPIC_WORKSPACE_ID`` is set we pass it; a plain workspace key works without
it.
"""

from __future__ import annotations

import os
from typing import Any


def make_client() -> Any:
    import anthropic

    headers: dict[str, str] = {}
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if workspace_id:
        headers["anthropic-workspace-id"] = workspace_id
    return anthropic.Anthropic(default_headers=headers or None)
