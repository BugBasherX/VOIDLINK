"""
VOIDLINK — Utility helpers.
"""

import uuid
import time
from typing import Optional


def new_uuid() -> str:
    """Generate a random UUID string."""
    return str(uuid.uuid4())


def now_ts() -> float:
    """Return current Unix timestamp as float."""
    return time.time()


def format_addr(host: str, port: int) -> str:
    """Format host and port as 'host:port'."""
    return f"{host}:{port}"


def parse_addr(addr: str) -> tuple[str, int]:
    """
    Parse 'host:port' string into (host, port).

    Raises:
        ValueError: if the format is invalid.
    """
    parts = addr.rsplit(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid address format '{addr}'. Expected host:port")
    host = parts[0].strip()
    try:
        port = int(parts[1].strip())
    except ValueError:
        raise ValueError(f"Port must be an integer, got '{parts[1]}'")
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} is out of range (1-65535)")
    return host, port


def short_id(uid: str, length: int = 8) -> str:
    """Return a shortened version of a UUID for display."""
    return uid[:length]


def human_uptime(seconds: float) -> str:
    """Format seconds into a human-readable uptime string."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


def truncate(text: str, max_len: int = 60) -> str:
    """Truncate a string with ellipsis if it exceeds max_len."""
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text
