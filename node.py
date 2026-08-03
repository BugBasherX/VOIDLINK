"""
VOIDLINK — Node entry point (v2: E2E encrypted, concurrent).

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

All inter-node communication is AES-256-GCM encrypted via ECDH-derived
session keys.  Every message is signed with Ed25519 to prove authorship.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import crypto
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

      NetworkManager  — Flask HTTP server + peer registry + encryption
      RoutingTable    — deduplication + flooding
      TTLManager      — background message expiry
      CLIHandler      — terminal command loop

    Each node generates a fresh Ed25519 identity keypair at startup.
    The keypair is ephemeral (in-memory only); persistence can be added later.
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        latency_ms: int = 0,
        packet_loss_pct: float = 0.0,
        advertise_host: Optional[str] = None,
        advertise_port: Optional[int] = None,
    ) -> None:
        self.node_id: str = node_id
        self.started_at: float = time.time()
        self.messages_sent_count: int = 0
        self.latency_ms: int = latency_ms
        self.packet_loss_pct: float = packet_loss_pct

        # Generate Ed25519 identity keypair for this session
        self.identity_private_key, self.identity_public_key = crypto.generate_identity()
        self.fingerprint: str = crypto.fingerprint(self.identity_public_key)

        # Build subsystems
        self.routing = RoutingTable(node_id=node_id)
        self.network = NetworkManager(
            node_id=node_id,
            host=host,
            port=port,
            routing=self.routing,
            identity_private_key=self.identity_private_key,
            identity_public_key=self.identity_public_key,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
            advertise_host=advertise_host,
            advertise_port=advertise_port,
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
            f"{APP_NAME} v{VERSION} — Node {self.node_id!r} | "
            f"fingerprint: {self.fingerprint}",
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
        self.network._executor.shutdown(wait=False)
        logger.info("Node shut down. Goodbye.", self.node_id)

    # ------------------------------------------------------------------ #
    # Messaging                                                            #
    # ------------------------------------------------------------------ #

    def send_message(self, content: str, ttl: int = 300) -> Message:
        """
        Create, sign, and propagate a new message originating from this node.

        The message is:
          1. Created with a fresh UUID and sender_id.
          2. Signed with this node's Ed25519 private key.
          3. Added to the local seen set (prevents self-forwarding loops).
          4. Stored in the local message store.
          5. Broadcast concurrently to all connected peers.
        """
        msg = Message.create(
            sender_id=self.node_id,
            content=content,
            ttl=ttl,
            private_key_bytes=self.identity_private_key,
            public_key_bytes=self.identity_public_key,
        )

        self.routing.mark_seen(msg.id)
        self.network.store_message(msg)
        self.ttl_manager.track(msg)

        self.network.broadcast(msg)
        self.messages_sent_count += 1

        return msg


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="node.py",
        description=f"{APP_NAME} — E2E encrypted distributed messaging node",
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
    parser.add_argument(
        "--advertise",
        default=None,
        metavar="HOST[:PORT]",
        help=(
            "Public address to advertise to peers. "
            "Use when behind NAT or a reverse proxy "
            "(e.g. --advertise mypublichost.example.com:443). "
            "On Replit: --advertise $REPLIT_DEV_DOMAIN:443"
        ),
    )
    return parser.parse_args()


def _parse_advertise(value: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    """Split 'host:port' advertise string into (host, port). Port is optional."""
    if not value:
        return None, None
    if ":" in value:
        host, _, port_str = value.rpartition(":")
        try:
            return host.strip(), int(port_str.strip())
        except ValueError:
            pass
    return value.strip(), None


if __name__ == "__main__":
    args = _parse_args()
    adv_host, adv_port = _parse_advertise(args.advertise)
    node = VoidlinkNode(
        node_id=args.id,
        host=args.host,
        port=args.port,
        latency_ms=args.latency,
        packet_loss_pct=args.loss,
        advertise_host=adv_host,
        advertise_port=adv_port,
    )
    node.start()
