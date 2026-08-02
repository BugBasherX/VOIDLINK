"""
VOIDLINK — Flood routing with loop prevention.

The routing table maintains a set of already-seen message UUIDs.
When a message arrives:
  1. If the UUID is already known → drop it (loop prevention).
  2. Otherwise → accept, store, and flood to all known peers
     (excluding the sender).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

import logger
from message import Message
from config import MAX_HOPS

if TYPE_CHECKING:
    from network import NetworkManager


class RoutingTable:
    """
    Manages deduplication and flooding of messages through the network.

    Thread-safe: all public methods acquire the internal lock before
    touching shared state.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id: str = node_id
        self._seen: set[str] = set()          # set of UUID strings
        self._lock: threading.Lock = threading.Lock()

        # Back-reference set by NetworkManager after construction
        self._network: Optional["NetworkManager"] = None

        # Counters
        self.messages_received: int = 0
        self.messages_forwarded: int = 0
        self.messages_dropped: int = 0

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_network(self, network: "NetworkManager") -> None:
        """Inject the NetworkManager dependency (called during startup)."""
        self._network = network

    def process(
        self,
        message: Message,
        source_addr: Optional[str] = None,
    ) -> bool:
        """
        Process an inbound (or locally originated) message.

        Returns True if the message was accepted and forwarded,
        False if it was a duplicate or exceeded MAX_HOPS.
        """
        with self._lock:
            # Deduplication check
            if message.id in self._seen:
                self.messages_dropped += 1
                return False

            # Hard-cap on hops
            if message.hop_count > MAX_HOPS:
                logger.error(
                    f"Message {message.short_id()} exceeded MAX_HOPS "
                    f"({MAX_HOPS}) — dropped.",
                    self.node_id,
                )
                self.messages_dropped += 1
                return False

            self._seen.add(message.id)

        # Track statistics (outside lock — already inserted)
        self.messages_received += 1

        # Log
        if source_addr:
            logger.recv(
                f"Message {message.short_id()} from {message.sender_id} "
                f"via {source_addr} "
                f"(hop {message.hop_count}, {message.seconds_remaining():.1f}s left)",
                self.node_id,
            )
        else:
            # Locally originated — log differently in cli.py / node.py
            pass

        # Flood to all peers except the one we got it from
        self._flood(message, exclude_addr=source_addr)
        return True

    def has_seen(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._seen

    def mark_seen(self, message_id: str) -> None:
        """Explicitly mark a message ID as seen (used for locally sent msgs)."""
        with self._lock:
            self._seen.add(message_id)

    def remove_seen(self, message_id: str) -> None:
        """
        Prune a message ID from the seen set once its TTL has expired.

        Called by TTLManager so the seen-set does not grow unbounded over
        long-running nodes.
        """
        with self._lock:
            self._seen.discard(message_id)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _flood(self, message: Message, exclude_addr: Optional[str]) -> None:
        """
        Forward *message* (with incremented hop count) to all known peers,
        optionally excluding the peer we received it from.
        """
        if self._network is None:
            return

        peers = self._network.get_peers()
        targets = [p for p in peers if p.address != exclude_addr]

        if not targets:
            return

        forwarded = message.forwarded()
        count = 0
        for p in targets:
            if self._network.send_to_peer(p, forwarded):
                count += 1

        if count:
            logger.fwd(
                f"Message {message.short_id()} forwarded to {count} peer(s)",
                self.node_id,
            )
            self.messages_forwarded += count
