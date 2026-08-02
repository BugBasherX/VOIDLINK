"""
VOIDLINK — Peer representation.

A Peer is a remote node that this node knows about.  It stores the
remote's advertised listen address so we can POST messages to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils import format_addr


@dataclass
class Peer:
    """Represents a known remote node."""

    node_id: str    # Remote node's identifier (e.g. "A", "B", …)
    host: str       # Remote listen host (as advertised by the peer)
    port: int       # Remote listen port

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def address(self) -> str:
        """Human-readable 'host:port' string."""
        return format_addr(self.host, self.port)

    @property
    def message_url(self) -> str:
        """Endpoint for posting a message to this peer."""
        return f"http://{self.host}:{self.port}/api/message"

    @property
    def hello_url(self) -> str:
        """Endpoint for sending a hello/connect handshake to this peer."""
        return f"http://{self.host}:{self.port}/api/hello"

    @property
    def bye_url(self) -> str:
        """Endpoint for sending a disconnect notification to this peer."""
        return f"http://{self.host}:{self.port}/api/bye"

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
        return f"Peer(id={self.node_id!r}, addr={self.address!r})"
