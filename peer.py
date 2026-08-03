"""
VOIDLINK — Peer representation.

A Peer is a remote node that this node knows about.  It stores the
remote's advertised listen address so we can POST messages to it.

Security additions (v2):
  * ``x25519_pub``  — remote node's ephemeral X25519 public key (raw bytes),
                      received during the /api/hello handshake.
  * ``session_key`` — 32-byte AES-256-GCM key derived via ECDH from
                      our X25519 private key + their X25519 public key.
                      All subsequent payloads to/from this peer are
                      encrypted with this key.
  * ``ed25519_pub`` — remote node's Ed25519 identity public key (raw bytes),
                      used to verify message signatures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from utils import format_addr


@dataclass
class Peer:
    """Represents a known remote node."""

    node_id: str    # Remote node's identifier (e.g. "A", "B", …)
    host: str       # Remote listen host (as advertised by the peer)
    port: int       # Remote listen port

    # Crypto fields — populated during handshake
    session_key: Optional[bytes] = field(default=None, repr=False)
    ed25519_pub: Optional[bytes] = field(default=None, repr=False)

    # Bookkeeping
    connected_at: float = field(default_factory=time.time, repr=False)

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def address(self) -> str:
        """Human-readable 'host:port' string."""
        return format_addr(self.host, self.port)

    @property
    def _scheme(self) -> str:
        """Use https when the peer is on port 443 (proxied/hosted node)."""
        return "https" if self.port == 443 else "http"

    @property
    def _base_url(self) -> str:
        """
        Base URL for this peer.

        - Port 443  → ``https://host``  (standard HTTPS, no port in URL)
        - Any other → ``http://host:port``
        """
        if self.port == 443:
            return f"https://{self.host}"
        return f"http://{self.host}:{self.port}"

    @property
    def message_url(self) -> str:
        """Endpoint for posting a message to this peer."""
        return f"{self._base_url}/api/message"

    @property
    def hello_url(self) -> str:
        """Endpoint for sending a hello/connect handshake to this peer."""
        return f"{self._base_url}/api/hello"

    @property
    def bye_url(self) -> str:
        """Endpoint for sending a disconnect notification to this peer."""
        return f"{self._base_url}/api/bye"

    @property
    def is_encrypted(self) -> bool:
        """True if a session key has been established with this peer."""
        return self.session_key is not None

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, str | int]:
        return {"node_id": self.node_id, "host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict) -> "Peer":
        return cls(
            node_id=str(data["node_id"]),
            host=str(data["host"]),
            port=int(data["port"]),
        )

    def __hash__(self) -> int:
        return hash(self.address)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Peer):
            return NotImplemented
        return self.address == other.address

    def __repr__(self) -> str:
        enc = " [E2E]" if self.is_encrypted else ""
        return f"Peer(id={self.node_id!r}, addr={self.address!r}{enc})"
