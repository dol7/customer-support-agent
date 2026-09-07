"""MCP tool return helpers.

An SDK MCP tool returns ``{"content": [...], "is_error": bool}``. These two
helpers keep every tool's success and failure shape identical, and keep the
error shape aligned with Week 1's ``{ok, errorCategory, isRetryable, message}``.

The distinction that matters downstream:

* ``err(...)`` sets ``is_error: True`` — the query could **not run**. It may be
  worth a retry (``retryable``), and the coordinator should treat it as a
  failure to route around.
* a plain ``ok({...})`` with an empty / negative payload is a **valid result** —
  the query ran and the answer is "nothing". Retrying returns the same nothing.
"""

from __future__ import annotations

import json
from typing import Any


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def err(
    category: str,
    retryable: bool,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    """A structured failure. ``extra`` typically carries ``attempted``,
    ``partialResults`` and ``alternatives`` so the coordinator can choose
    between retry, skip-and-flag, and escalate."""
    payload = {
        "ok": False,
        "errorCategory": category,
        "isRetryable": retryable,
        "message": message,
        **extra,
    }
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "is_error": True,
    }
