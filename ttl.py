"""
VOIDLINK — TTL (time-to-live) expiration manager.

Runs a background daemon thread that periodically scans the in-memory
message store, expires messages whose TTL has elapsed, and removes
them from both the local store and the routing seen-set so that the
log stays tidy.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import logger
from config import MESSAGE_CHECK_INTERVAL
from message import Message

if TYPE_CHECKING:
    from network import NetworkManager


class TTLManager:
    """
    Background janitor that expires messages past their TTL.

    Usage::

        tm = TTLManager(node_id="A", network=network_manager)
        tm.start()
    """

    def __init__(self, node_id: str, network: "NetworkManager") -> None:
        self.node_id: str = node_id
        self._network: "NetworkManager" = network
        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None

        # Statistics
        self.messages_expired: int = 0

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the background TTL checker thread."""
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"ttl-{self.node_id}",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to exit."""
        self._stop_event.set()

    # ------------------------------------------------------------------ #
    # Tracking                                                             #
    # ------------------------------------------------------------------ #

    def track(self, message: Message) -> None:
        """
        Explicitly register a message to be watched for expiry.

        In practice messages land in the network's message store via
        NetworkManager.store_message(); this method exists as a hook
        for any future explicit registration logic.
        """
        # No-op: the janitor scans network.messages directly.
        pass

    # ------------------------------------------------------------------ #
    # Background loop                                                      #
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._expire_messages()
            self._stop_event.wait(timeout=MESSAGE_CHECK_INTERVAL)

    def _expire_messages(self) -> None:
        expired: list[Message] = []

        # Take a snapshot to avoid holding the lock during logging
        messages = self._network.get_messages()
        for msg in messages:
            if msg.is_expired():
                expired.append(msg)

        for msg in expired:
            removed = self._network.remove_message(msg.id)
            if removed is not None:
                logger.ttl(
                    f"Message {msg.short_id()}… expired and deleted from memory",
                    self.node_id,
                )
                self.messages_expired += 1
                # Prune from routing seen-set so the set doesn't grow unbounded
                self._network.routing.remove_seen(msg.id)
