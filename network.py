"""
VOIDLINK — Network manager.

Responsibilities:
  * Run a Flask HTTP server that accepts inbound messages and peer
    handshakes from other nodes.
  * Maintain the registry of known peers.
  * Send outbound HTTP POST requests to peers.

REST endpoints exposed:
  POST /api/hello    — peer announces itself (connect handshake)
  POST /api/bye      — peer announces disconnect
  POST /api/message  — receive a propagated message
  GET  /api/peers    — list all known peers (diagnostic)
  GET  /api/healthz  — liveness probe
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

import requests
from flask import Flask, request, jsonify

import logger
from config import REQUEST_TIMEOUT
from message import Message
from peer import Peer

if TYPE_CHECKING:
    from routing import RoutingTable
    from ttl import TTLManager


class NetworkManager:
    """
    Manages the Flask HTTP server and the peer registry.

    Thread-safe: peer registry access is protected by a RLock.
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        routing: "RoutingTable",
        latency_ms: int = 0,
        packet_loss_pct: float = 0.0,
    ) -> None:
        self.node_id: str = node_id
        self.host: str = host
        self.port: int = port
        self.routing: "RoutingTable" = routing
        self.latency_ms: int = latency_ms          # artificial delay per send (ms)
        self.packet_loss_pct: float = packet_loss_pct  # 0.0–100.0 drop probability

        # Message store: id → Message (populated by routing + ttl_manager)
        self.messages: dict[str, Message] = {}
        self.messages_lock: threading.Lock = threading.Lock()

        # Peer registry: address → Peer
        self._peers: dict[str, Peer] = {}
        self._peers_lock: threading.RLock = threading.RLock()

        # Back-ref injected after TTLManager is created
        self._ttl_manager: Optional["TTLManager"] = None

        # Statistics
        self.messages_sent: int = 0

        self._app: Flask = self._build_app()
        self._server_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Startup / shutdown                                                   #
    # ------------------------------------------------------------------ #

    def set_ttl_manager(self, ttl_manager: "TTLManager") -> None:
        self._ttl_manager = ttl_manager

    def start(self) -> None:
        """Launch Flask server in a background daemon thread."""
        self._server_thread = threading.Thread(
            target=self._run_flask,
            daemon=True,
            name=f"flask-{self.node_id}",
        )
        self._server_thread.start()
        # Give Flask a moment to bind before the CLI starts
        time.sleep(0.5)
        logger.info(
            f"Listening on {self.host}:{self.port}",
            self.node_id,
        )

    def _run_flask(self) -> None:
        import logging as pylogging
        pylogging.getLogger("werkzeug").setLevel(pylogging.ERROR)
        self._app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    # ------------------------------------------------------------------ #
    # Flask application                                                    #
    # ------------------------------------------------------------------ #

    def _build_app(self) -> Flask:
        app = Flask(f"voidlink-{self.node_id}")
        app.logger.disabled = True

        nm = self  # closure reference

        @app.route("/api/healthz", methods=["GET"])
        def healthz():
            return jsonify({"status": "ok", "node_id": nm.node_id})

        @app.route("/api/peers", methods=["GET"])
        def list_peers():
            with nm._peers_lock:
                return jsonify([p.to_dict() for p in nm._peers.values()])

        @app.route("/api/hello", methods=["POST"])
        def hello():
            """Peer sends us its node_id + listen address."""
            data = request.get_json(silent=True) or {}
            peer_id = data.get("node_id", "UNKNOWN")
            peer_host = data.get("host", request.remote_addr)
            peer_port = int(data.get("port", 0))

            if peer_port == 0:
                return jsonify({"error": "missing port"}), 400

            p = Peer(node_id=peer_id, host=peer_host, port=peer_port)
            added = nm._register_peer(p)
            if added:
                logger.peer(
                    f"Peer {peer_id} connected from {p.address}",
                    nm.node_id,
                )
            return jsonify({"node_id": nm.node_id, "status": "ok"})

        @app.route("/api/bye", methods=["POST"])
        def bye():
            """Peer notifies us it is disconnecting."""
            data = request.get_json(silent=True) or {}
            peer_host = data.get("host", request.remote_addr)
            peer_port = int(data.get("port", 0))
            addr = f"{peer_host}:{peer_port}"
            removed = nm._remove_peer_by_addr(addr)
            if removed:
                logger.peer(
                    f"Peer {removed.node_id} disconnected ({addr})",
                    nm.node_id,
                )
            return jsonify({"status": "ok"})

        @app.route("/api/message", methods=["POST"])
        def receive_message():
            """Receive a propagated message from a peer."""
            data = request.get_json(silent=True) or {}
            try:
                msg = Message.from_dict(data)
            except (KeyError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

            source_addr = data.get("_source_addr", request.remote_addr)

            # Store the message if accepted
            if nm.routing.process(msg, source_addr=source_addr):
                with nm.messages_lock:
                    nm.messages[msg.id] = msg
                if nm._ttl_manager:
                    nm._ttl_manager.track(msg)

            return jsonify({"status": "ok"})

        return app

    # ------------------------------------------------------------------ #
    # Peer registry                                                        #
    # ------------------------------------------------------------------ #

    def _register_peer(self, peer: Peer) -> bool:
        """Add peer to the registry. Returns True if newly added."""
        with self._peers_lock:
            if peer.address in self._peers:
                return False
            self._peers[peer.address] = peer
            return True

    def _remove_peer_by_addr(self, addr: str) -> Optional[Peer]:
        """Remove and return peer by address, or None if not found."""
        with self._peers_lock:
            return self._peers.pop(addr, None)

    def get_peers(self) -> list[Peer]:
        """Return a snapshot of current peers."""
        with self._peers_lock:
            return list(self._peers.values())

    def get_peer_by_addr(self, addr: str) -> Optional[Peer]:
        with self._peers_lock:
            return self._peers.get(addr)

    # ------------------------------------------------------------------ #
    # Connect / disconnect                                                 #
    # ------------------------------------------------------------------ #

    def connect_to(self, host: str, port: int) -> tuple[bool, str]:
        """
        Initiate a connection to a remote peer.

        Sends a POST /api/hello to the remote node with our address,
        and registers the peer locally on success.

        Returns (success, message).
        """
        addr = f"{host}:{port}"
        with self._peers_lock:
            if addr in self._peers:
                return False, f"Already connected to {addr}"

        payload = {
            "node_id": self.node_id,
            "host": self._advertised_host(),
            "port": self.port,
        }
        url = f"http://{host}:{port}/api/hello"
        try:
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.ConnectionError:
            return False, f"Connection refused at {addr}"
        except requests.Timeout:
            return False, f"Timeout connecting to {addr}"
        except Exception as exc:
            return False, f"Error: {exc}"

        remote_id = data.get("node_id", "UNKNOWN")
        peer = Peer(node_id=remote_id, host=host, port=port)
        self._register_peer(peer)
        return True, remote_id

    def disconnect_from(self, host: str, port: int) -> tuple[bool, str]:
        """
        Disconnect from a peer gracefully.

        Returns (success, message).
        """
        addr = f"{host}:{port}"
        peer = self.get_peer_by_addr(addr)
        if peer is None:
            return False, f"Not connected to {addr}"

        payload = {
            "host": self._advertised_host(),
            "port": self.port,
        }
        try:
            requests.post(peer.bye_url, json=payload, timeout=REQUEST_TIMEOUT)
        except Exception:
            pass  # Best-effort notification; we still remove locally

        self._remove_peer_by_addr(addr)
        return True, peer.node_id

    # ------------------------------------------------------------------ #
    # Sending                                                              #
    # ------------------------------------------------------------------ #

    def send_to_peer(self, peer: Peer, message: Message) -> bool:
        """
        POST a message to a single peer.

        Applies artificial latency and packet-loss simulation when configured.
        Returns True on success, False on failure (and removes the
        unreachable peer from the registry).
        """
        import random

        # Packet-loss simulation: randomly drop the message before sending
        if self.packet_loss_pct > 0.0:
            if random.uniform(0.0, 100.0) < self.packet_loss_pct:
                logger.fwd(
                    f"[SIM] Packet to {peer.node_id} dropped "
                    f"({self.packet_loss_pct:.0f}% loss)",
                    self.node_id,
                )
                return False

        # Latency simulation: block this thread before sending
        if self.latency_ms > 0:
            import time
            time.sleep(self.latency_ms / 1000.0)

        payload = message.to_dict()
        payload["_source_addr"] = f"{self._advertised_host()}:{self.port}"
        try:
            resp = requests.post(
                peer.message_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            self.messages_sent += 1
            return True
        except requests.ConnectionError:
            logger.error(
                f"Peer {peer.node_id} ({peer.address}) unreachable — removing",
                self.node_id,
            )
            self._remove_peer_by_addr(peer.address)
            return False
        except Exception as exc:
            logger.error(f"Send to {peer.address} failed: {exc}", self.node_id)
            return False

    def broadcast(self, message: Message, exclude_addr: Optional[str] = None) -> int:
        """
        Send *message* to all known peers (except *exclude_addr*).

        Returns the number of peers successfully reached.
        """
        peers = [p for p in self.get_peers() if p.address != exclude_addr]
        count = sum(1 for p in peers if self.send_to_peer(p, message))
        return count

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _advertised_host(self) -> str:
        """
        Return the host address we advertise to peers.
        If we're binding on 0.0.0.0 we advertise 127.0.0.1 so that
        peers on the same machine can reach us.
        """
        if self.host in ("0.0.0.0", ""):
            return "127.0.0.1"
        return self.host

    def store_message(self, msg: Message) -> None:
        """Store a message in the local message store."""
        with self.messages_lock:
            self.messages[msg.id] = msg

    def remove_message(self, msg_id: str) -> Optional[Message]:
        """Remove and return a message from the store."""
        with self.messages_lock:
            return self.messages.pop(msg_id, None)

    def get_messages(self) -> list[Message]:
        """Return a snapshot of all stored messages."""
        with self.messages_lock:
            return list(self.messages.values())
