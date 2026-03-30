"""
Shared process-management helpers for app-owned worker infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    """Returns the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def read_log_tail(log_path: Path, max_chars: int = 400) -> str:
    """
    Returns the trailing slice of a log file for crash diagnostics.

    Args:
        log_path: Log file to read.
        max_chars: Maximum trailing character count.

    Returns:
        Trailing log text, or an empty string when unavailable.
    """
    if not log_path.exists():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    return text[-max_chars:].strip()
