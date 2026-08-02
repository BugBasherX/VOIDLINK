"""
VOIDLINK — Message data structure.

Each message is ephemeral: it carries a TTL (time-to-live in seconds),
a hop count, and a UUID that nodes use for deduplication.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any

from utils import new_uuid, now_ts
from config import DEFAULT_TTL


@dataclass
class Message:
    """Represents a single VOIDLINK message in flight."""

    id: str               # UUID — globally unique message identifier
    sender_id: str        # Node ID of the original sender
    content: str          # Human-readable payload
    timestamp: float      # Unix time when the message was originally created
    ttl: int              # Seconds until the message expires (from creation time)
    hop_count: int        # Number of hops taken so far

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(
        cls,
        sender_id: str,
        content: str,
        ttl: int = DEFAULT_TTL,
    ) -> "Message":
        """Create a brand-new message originating from *sender_id*."""
        return cls(
            id=new_uuid(),
            sender_id=sender_id,
            content=content,
            timestamp=now_ts(),
            ttl=ttl,
            hop_count=0,
        )

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON transport."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        """Deserialise from a plain dict (e.g. parsed JSON body)."""
        return cls(
            id=data["id"],
            sender_id=data["sender_id"],
            content=data["content"],
            timestamp=float(data["timestamp"]),
            ttl=int(data["ttl"]),
            hop_count=int(data["hop_count"]),
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def is_expired(self) -> bool:
        """Return True if the message has exceeded its TTL."""
        return (now_ts() - self.timestamp) >= self.ttl

    def seconds_remaining(self) -> float:
        """Return seconds left before expiry (may be negative if already expired)."""
        return self.ttl - (now_ts() - self.timestamp)

    def forwarded(self) -> "Message":
        """Return a copy of this message with hop_count incremented by 1."""
        return Message(
            id=self.id,
            sender_id=self.sender_id,
            content=self.content,
            timestamp=self.timestamp,
            ttl=self.ttl,
            hop_count=self.hop_count + 1,
        )

    def short_id(self, length: int = 8) -> str:
        """Return a shortened message ID for display."""
        return self.id[:length]

    def __repr__(self) -> str:
        return (
            f"Message(id={self.short_id()!r}, sender={self.sender_id!r}, "
            f"hops={self.hop_count}, ttl={self.ttl}s, "
            f"remaining={max(0.0, self.seconds_remaining()):.1f}s)"
        )
