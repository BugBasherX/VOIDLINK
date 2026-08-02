"""
VOIDLINK — Node entry point.

Usage::

    python node.py --id A --port 5000
    python node.py --id B --port 5001
    python node.py --id C --port 5002 --host 0.0.0.0

Inside the REPL you can then type commands such as::

    /connect localhost:5001
    /send Hello Network
    /peers
    /stats
    /quit
"""

from __future__ import annotations

import argparse
import sys
import time

import logger
from config import (
    APP_NAME,
    VERSION,
    BANNER,
    DEFAULT_HOST,
    DEFAULT_PORT,
)
from message import Message
from network import NetworkManager
from routing import RoutingTable
from ttl import TTLManager
from cli import CLIHandler
from utils import new_uuid


class VoidlinkNode:
    """
    Top-level coordinator that wires together all subsystems:

      NetworkManager  — Flask HTTP server + peer registry
      RoutingTable    — deduplication + flooding
      TTLManager      — background message expiry
      CLIHandler      — terminal command loop
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        latency_ms: int = 0,
        packet_loss_pct: float = 0.0,
    ) -> None:
        self.node_id: str = node_id
        self.started_at: float = time.time()
        self.messages_sent_count: int = 0
        self.latency_ms: int = latency_ms
        self.packet_loss_pct: float = packet_loss_pct

        # Build subsystems
        self.routing = RoutingTable(node_id=node_id)
        self.network = NetworkManager(
            node_id=node_id,
            host=host,
            port=port,
            routing=self.routing,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
        )
        self.ttl_manager = TTLManager(node_id=node_id, network=self.network)
        self.cli = CLIHandler(node=self)

        # Wire cross-references
        self.routing.set_network(self.network)
        self.network.set_ttl_manager(self.ttl_manager)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start all background services and launch the CLI."""
        logger.banner(BANNER)
        logger.info(
            f"{APP_NAME} v{VERSION} — Node {self.node_id!r} starting up",
            self.node_id,
        )

        self.network.start()
        self.ttl_manager.start()

        logger.info("Type /help for a list of commands.", self.node_id)
        self.cli.run()

    def shutdown(self) -> None:
        """Gracefully notify all peers we are leaving."""
        logger.info("Notifying peers of disconnect…", self.node_id)
        for p in self.network.get_peers():
            try:
                self.network.disconnect_from(p.host, p.port)
            except Exception:
                pass
        self.ttl_manager.stop()
        logger.info("Node shut down. Goodbye.", self.node_id)

    # ------------------------------------------------------------------ #
    # Messaging                                                            #
    # ------------------------------------------------------------------ #

    def send_message(self, content: str, ttl: int = 10) -> Message:
        """
        Create and propagate a new message originating from this node.

        The message is:
          1. Created with a fresh UUID and the node's sender_id.
          2. Added to the local seen set (prevents self-forwarding loops).
          3. Stored in the local message store.
          4. Broadcast to all connected peers.
        """
        msg = Message.create(sender_id=self.node_id, content=content, ttl=ttl)

        # Mark seen immediately so we don't re-process our own message
        self.routing.mark_seen(msg.id)

        # Store locally
        self.network.store_message(msg)
        self.ttl_manager.track(msg)

        # Flood to peers
        count = self.network.broadcast(msg)
        self.messages_sent_count += 1

        return msg


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="node.py",
        description=f"{APP_NAME} — CLI distributed messaging node",
    )
    parser.add_argument(
        "--id",
        metavar="NODE_ID",
        required=True,
        help="Unique identifier for this node (e.g. A, B, NodeAlpha)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host/interface to bind to (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--latency",
        type=int,
        default=0,
        metavar="MS",
        help="Artificial send latency in milliseconds (default: 0)",
    )
    parser.add_argument(
        "--loss",
        type=float,
        default=0.0,
        metavar="PCT",
        help="Simulated packet-loss percentage 0–100 (default: 0)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    node = VoidlinkNode(
        node_id=args.id,
        host=args.host,
        port=args.port,
        latency_ms=args.latency,
        packet_loss_pct=args.loss,
    )
    node.start()
