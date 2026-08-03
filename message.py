"""
VOIDLINK — Message data structure.

Each message is ephemeral: it carries a TTL (time-to-live in seconds),
a hop count, and a UUID that nodes use for deduplication.

Security additions (v2):
  * ``signature`` — Ed25519 signature over canonical message fields.
    Proves the message was created by the node that owns the signing key.
  * ``sender_pubkey`` — hex-encoded Ed25519 public key of the originator,
    carried with the message so any recipient can verify without a separate
    key-distribution channel.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import crypto
from utils import new_uuid, now_ts
from config import DEFAULT_TTL


def _signing_blob(
    msg_id: str,
    sender_id: str,
    content: str,
    timestamp: float,
    ttl: int,
) -> bytes:
    """
    Canonical byte string that is signed / verified.

    We include all fields that must not be tampered with.
    hop_count is intentionally excluded — it changes at every hop.
    """
    return (
        f"{msg_id}|{sender_id}|{content}|{timestamp:.6f}|{ttl}"
    ).encode()


@dataclass
class Message:
    """Represents a single VOIDLINK message in flight."""

    id: str               # UUID — globally unique message identifier
    sender_id: str        # Node ID of the original sender
    content: str          # Human-readable payload
    timestamp: float      # Unix time when the message was originally created
    ttl: int              # Seconds until the message expires (from creation time)
    hop_count: int        # Number of hops taken so far

    # Security fields (optional — absent on older / unencrypted nodes)
    signature: str = ""          # base64url Ed25519 signature
    sender_pubkey: str = ""      # hex Ed25519 public key of originator

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(
        cls,
        sender_id: str,
        content: str,
        ttl: int = DEFAULT_TTL,
        private_key_bytes: Optional[bytes] = None,
        public_key_bytes: Optional[bytes] = None,
    ) -> "Message":
        """
        Create a brand-new message originating from *sender_id*.

        If *private_key_bytes* is supplied the message is signed immediately.
        """
        msg = cls(
            id=new_uuid(),
            sender_id=sender_id,
            content=content,
            timestamp=now_ts(),
            ttl=ttl,
            hop_count=0,
        )
        if private_key_bytes and public_key_bytes:
            msg.sign(private_key_bytes, public_key_bytes)
        return msg

    # ------------------------------------------------------------------ #
    # Signing / verification                                               #
    # ------------------------------------------------------------------ #

    def sign(self, private_key_bytes: bytes, public_key_bytes: bytes) -> None:
        """Sign this message in-place using the sender's Ed25519 private key."""
        blob = _signing_blob(
            self.id, self.sender_id, self.content, self.timestamp, self.ttl
        )
        sig_bytes = crypto.sign(blob, private_key_bytes)
        self.signature = crypto.b64enc(sig_bytes)
        self.sender_pubkey = public_key_bytes.hex()

    def verify(self) -> bool:
        """
        Verify the Ed25519 signature.

        Returns False (rather than raising) if anything is missing or invalid.
        """
        if not self.signature or not self.sender_pubkey:
            return False
        try:
            blob = _signing_blob(
                self.id, self.sender_id, self.content, self.timestamp, self.ttl
            )
            sig_bytes = crypto.b64dec(self.signature)
            pub_bytes = bytes.fromhex(self.sender_pubkey)
            return crypto.verify(blob, sig_bytes, pub_bytes)
        except Exception:
            return False

    @property
    def is_signed(self) -> bool:
        """True if this message carries a signature field (not necessarily valid)."""
        return bool(self.signature)

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON transport."""
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "content": self.content,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "hop_count": self.hop_count,
            "signature": self.signature,
            "sender_pubkey": self.sender_pubkey,
        }

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
            signature=str(data.get("signature", "")),
            sender_pubkey=str(data.get("sender_pubkey", "")),
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
            signature=self.signature,
            sender_pubkey=self.sender_pubkey,
        )

    def short_id(self, length: int = 8) -> str:
        """Return a shortened message ID for display."""
        return self.id[:length]

    def __repr__(self) -> str:
        sig = "✓" if self.is_signed else "✗"
        return (
            f"Message(id={self.short_id()!r}, sender={self.sender_id!r}, "
            f"hops={self.hop_count}, ttl={self.ttl}s, "
            f"remaining={max(0.0, self.seconds_remaining()):.1f}s, sig={sig})"
        )
