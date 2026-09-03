"""Customer support resolution agent — hand-written Messages API tool loop."""

from .agent import Result, run_conversation
from .backend import SessionContext
from .errors import (
    LoopSafetyCapExceeded,
    MaxTokensError,
    UnexpectedStopReason,
)

__all__ = [
    "Result",
    "run_conversation",
    "SessionContext",
    "LoopSafetyCapExceeded",
    "MaxTokensError",
    "UnexpectedStopReason",
]
