"""
VOIDLINK — Network manager (v2: encrypted + concurrent).

Responsibilities:
  * Run a Flask HTTP server that accepts inbound messages and peer
    handshakes from other nodes.
  * Maintain the registry of known peers.
  * Send outbound HTTP requests to peers — concurrently via a
    ThreadPoolExecutor, with exponential-backoff retry.
  * Perform X25519 ECDH key exchange on /api/hello so that all
    subsequent peer communication is AES-256-GCM encrypted.
  * Reject messages whose Ed25519 signature is invalid.

REST endpoints exposed:
  POST /api/hello    — peer announces itself + exchanges X25519 public key
  POST /api/bye      — peer announces disconnect (encrypted)
  POST /api/message  — receive a propagated message (encrypted)
  GET  /api/peers    — list all known peers (diagnostic)
  GET  /api/healthz  — liveness probe

Payload envelope (v2):
  All POST bodies after the initial hello are wrapped as:
    { "enc": "<base64url(iv + ciphertext + tag)>", "from": "<node_id>" }
  The receiver looks up the session key by sender node_id and decrypts.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Optional

import requests
import requests.adapters
from flask import Flask, request, jsonify

import crypto
import logger
from config import (
    REQUEST_TIMEOUT,
    BROADCAST_WORKERS,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF,
    CONNECTION_POOL_SIZE,
    CRYPTO_ENABLED,
)
from message import Message
from peer import Peer

if TYPE_CHECKING:
    from routing import RoutingTable
    from ttl import TTLManager


class NetworkManager:
    """
    Manages the Flask HTTP server, the peer registry, and all outbound sends.

    Thread-safe: peer registry access is protected by an RLock.
    """

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        routing: "RoutingTable",
        identity_private_key: bytes,
        identity_public_key: bytes,
        latency_ms: int = 0,
        packet_loss_pct: float = 0.0,
    ) -> None:
        self.node_id: str = node_id
        self.host: str = host
        self.port: int = port
        self.routing: "RoutingTable" = routing
        self.latency_ms: int = latency_ms
        self.packet_loss_pct: float = packet_loss_pct

        # Our Ed25519 identity (for signing messages we originate)
        self._identity_priv: bytes = identity_private_key
        self._identity_pub: bytes = identity_public_key

        # Our ephemeral X25519 keypair for ECDH (one per process lifetime)
        self._x25519_priv, self._x25519_pub = crypto.generate_x25519_keypair()

        # Message store: id → Message
        self.messages: dict[str, Message] = {}
        self.messages_lock: threading.Lock = threading.Lock()

        # Peer registry: address → Peer
        self._peers: dict[str, Peer] = {}
        self._peers_lock: threading.RLock = threading.RLock()

        # node_id → Peer index for fast lookup during decryption
        self._peers_by_id: dict[str, Peer] = {}

        # Back-ref injected after TTLManager is created
        self._ttl_manager: Optional["TTLManager"] = None

        # Statistics
        self.messages_sent: int = 0
        self.messages_rejected: int = 0

        # Persistent HTTP session with connection pooling
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=CONNECTION_POOL_SIZE,
            pool_maxsize=CONNECTION_POOL_SIZE,
            max_retries=0,  # we handle retries ourselves
        )
        self._session.mount("http://", adapter)

        # Thread pool for concurrent broadcasts
        self._executor = ThreadPoolExecutor(
            max_workers=BROADCAST_WORKERS,
            thread_name_prefix=f"vl-send-{node_id}",
        )

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
        time.sleep(0.5)
        logger.info(
            f"Listening on {self.host}:{self.port}  "
            f"| fingerprint {crypto.fingerprint(self._identity_pub)}",
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
        nm = self

        @app.route("/api/healthz", methods=["GET"])
        def healthz():
            return jsonify({
                "status": "ok",
                "node_id": nm.node_id,
                "encrypted": CRYPTO_ENABLED,
            })

        @app.route("/api/peers", methods=["GET"])
        def list_peers():
            with nm._peers_lock:
                return jsonify([p.to_dict() for p in nm._peers.values()])

        @app.route("/api/hello", methods=["POST"])
        def hello():
            """
            Peer handshake — exchange node info and X25519 public keys.

            Payload (plaintext — no session key exists yet):
              { node_id, host, port, x25519_pub: hex, ed25519_pub: hex }
            Response:
              { node_id, status, x25519_pub: hex, ed25519_pub: hex }
            """
            data = request.get_json(silent=True) or {}
            peer_id   = data.get("node_id", "UNKNOWN")
            peer_host = data.get("host", request.remote_addr)
            peer_port = int(data.get("port", 0))

            if peer_port == 0:
                return jsonify({"error": "missing port"}), 400

            p = Peer(node_id=peer_id, host=peer_host, port=peer_port)

            # ECDH key exchange — derive a session key for this peer
            if CRYPTO_ENABLED:
                their_x25519_hex = data.get("x25519_pub", "")
                their_ed25519_hex = data.get("ed25519_pub", "")
                if their_x25519_hex:
                    try:
                        their_x25519 = bytes.fromhex(their_x25519_hex)
                        p.session_key = crypto.derive_session_key(
                            nm._x25519_priv, their_x25519
                        )
                        if their_ed25519_hex:
                            p.ed25519_pub = bytes.fromhex(their_ed25519_hex)
                    except Exception as exc:
                        logger.error(f"Key exchange with {peer_id} failed: {exc}", nm.node_id)

            added = nm._register_peer(p)
            if added:
                logger.peer(
                    f"Peer {peer_id} connected from {p.address}"
                    + (" [E2E encrypted]" if p.is_encrypted else " [plaintext]"),
                    nm.node_id,
                )

            response: dict = {"node_id": nm.node_id, "status": "ok"}
            if CRYPTO_ENABLED:
                response["x25519_pub"] = nm._x25519_pub.hex()
                response["ed25519_pub"] = nm._identity_pub.hex()
            return jsonify(response)

        @app.route("/api/bye", methods=["POST"])
        def bye():
            """Peer notifies us it is disconnecting."""
            data = nm._recv_payload(request)
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
            data = nm._recv_payload(request)
            if data is None:
                nm.messages_rejected += 1
                return jsonify({"error": "decryption failed"}), 403

            try:
                msg = Message.from_dict(data)
            except (KeyError, ValueError) as exc:
                nm.messages_rejected += 1
                return jsonify({"error": str(exc)}), 400

            # Verify Ed25519 signature
            if CRYPTO_ENABLED and msg.is_signed:
                if not msg.verify():
                    nm.messages_rejected += 1
                    logger.error(
                        f"Message {msg.short_id()} FAILED signature check — dropped",
                        nm.node_id,
                    )
                    return jsonify({"error": "invalid signature"}), 403

            source_addr = data.get("_source_addr", request.remote_addr)

            if nm.routing.process(msg, source_addr=source_addr):
                with nm.messages_lock:
                    nm.messages[msg.id] = msg
                if nm._ttl_manager:
                    nm._ttl_manager.track(msg)

            return jsonify({"status": "ok"})

        return app

    # ------------------------------------------------------------------ #
    # Payload encryption / decryption helpers                             #
    # ------------------------------------------------------------------ #

    def _send_payload(self, peer: Peer, data: dict) -> dict:
        """
        Wrap *data* in an encrypted envelope for *peer* if a session key
        exists, otherwise return *data* unchanged (plaintext fallback).
        """
        if CRYPTO_ENABLED and peer.session_key:
            plaintext = json.dumps(data).encode()
            enc_bytes = crypto.encrypt(plaintext, peer.session_key)
            return {"enc": crypto.b64enc(enc_bytes), "from": self.node_id}
        return data

    def _recv_payload(self, req) -> Optional[dict]:
        """
        Decode an inbound request body.

        If the body is an encrypted envelope, look up the sender's session
        key, decrypt, and return the inner dict.  Returns None if
        decryption fails (caller should reject with 403).
        """
        raw = req.get_json(silent=True) or {}

        if "enc" not in raw:
            # Plaintext (no session key negotiated — or crypto disabled)
            return raw

        sender_id = raw.get("from", "")
        peer = self._get_peer_by_node_id(sender_id)

        if peer is None or peer.session_key is None:
            # Unknown peer or no key — try all registered peers as fallback
            # (handles race where address changed but id is known)
            with self._peers_lock:
                for p in self._peers.values():
                    if p.session_key:
                        try:
                            raw_bytes = crypto.b64dec(raw["enc"])
                            plaintext = crypto.decrypt(raw_bytes, p.session_key)
                            return json.loads(plaintext)
                        except Exception:
                            continue
            return None

        try:
            raw_bytes = crypto.b64dec(raw["enc"])
            plaintext = crypto.decrypt(raw_bytes, peer.session_key)
            return json.loads(plaintext)
        except Exception as exc:
            logger.error(
                f"Decryption from {sender_id} failed: {exc}", self.node_id
            )
            return None

    # ------------------------------------------------------------------ #
    # Peer registry                                                        #
    # ------------------------------------------------------------------ #

    def _register_peer(self, peer: Peer) -> bool:
        """Add peer to the registry. Returns True if newly added."""
        with self._peers_lock:
            if peer.address in self._peers:
                # Update crypto fields if we now have them
                existing = self._peers[peer.address]
                if peer.session_key and not existing.session_key:
                    existing.session_key = peer.session_key
                    existing.ed25519_pub = peer.ed25519_pub
                    self._peers_by_id[peer.node_id] = existing
                return False
            self._peers[peer.address] = peer
            self._peers_by_id[peer.node_id] = peer
            return True

    def _remove_peer_by_addr(self, addr: str) -> Optional[Peer]:
        """Remove and return peer by address, or None if not found."""
        with self._peers_lock:
            peer = self._peers.pop(addr, None)
            if peer:
                self._peers_by_id.pop(peer.node_id, None)
            return peer

    def _get_peer_by_node_id(self, node_id: str) -> Optional[Peer]:
        with self._peers_lock:
            return self._peers_by_id.get(node_id)

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

        Sends POST /api/hello with our identity + X25519 public key,
        derives the shared session key from the response, and registers
        the peer locally.

        Returns (success, message).
        """
        addr = f"{host}:{port}"
        with self._peers_lock:
            if addr in self._peers:
                return False, f"Already connected to {addr}"

        payload: dict = {
            "node_id": self.node_id,
            "host": self._advertised_host(),
            "port": self.port,
        }
        if CRYPTO_ENABLED:
            payload["x25519_pub"] = self._x25519_pub.hex()
            payload["ed25519_pub"] = self._identity_pub.hex()

        url = f"http://{host}:{port}/api/hello"
        try:
            resp = self._session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
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

        # ECDH: derive session key from remote's X25519 public key
        if CRYPTO_ENABLED:
            their_x25519_hex = data.get("x25519_pub", "")
            their_ed25519_hex = data.get("ed25519_pub", "")
            if their_x25519_hex:
                try:
                    their_x25519 = bytes.fromhex(their_x25519_hex)
                    peer.session_key = crypto.derive_session_key(
                        self._x25519_priv, their_x25519
                    )
                    if their_ed25519_hex:
                        peer.ed25519_pub = bytes.fromhex(their_ed25519_hex)
                except Exception as exc:
                    logger.error(
                        f"Key exchange with {remote_id} failed: {exc}", self.node_id
                    )

        self._register_peer(peer)
        return True, remote_id

    def disconnect_from(self, host: str, port: int) -> tuple[bool, str]:
        """Disconnect from a peer gracefully.  Returns (success, message)."""
        addr = f"{host}:{port}"
        peer = self.get_peer_by_addr(addr)
        if peer is None:
            return False, f"Not connected to {addr}"

        payload = {"host": self._advertised_host(), "port": self.port}
        try:
            envelope = self._send_payload(peer, payload)
            self._session.post(peer.bye_url, json=envelope, timeout=REQUEST_TIMEOUT)
        except Exception:
            pass  # best-effort; still remove locally

        self._remove_peer_by_addr(addr)
        return True, peer.node_id

    # ------------------------------------------------------------------ #
    # Sending — with retry / backoff / concurrent broadcast               #
    # ------------------------------------------------------------------ #

    def send_to_peer(self, peer: Peer, message: Message) -> bool:
        """
        POST a message to a single peer, with retry + exponential backoff.

        Applies artificial latency and packet-loss simulation if configured.
        Returns True on success, False on final failure (peer removed).
        """
        import random

        if self.packet_loss_pct > 0.0:
            if random.uniform(0.0, 100.0) < self.packet_loss_pct:
                logger.fwd(
                    f"[SIM] Packet to {peer.node_id} dropped "
                    f"({self.packet_loss_pct:.0f}% loss)",
                    self.node_id,
                )
                return False

        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        payload = message.to_dict()
        payload["_source_addr"] = f"{self._advertised_host()}:{self.port}"
        envelope = self._send_payload(peer, payload)

        for attempt in range(RETRY_ATTEMPTS):
            try:
                resp = self._session.post(
                    peer.message_url,
                    json=envelope,
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                self.messages_sent += 1
                return True
            except requests.ConnectionError:
                if attempt < RETRY_ATTEMPTS - 1:
                    backoff = RETRY_BACKOFF * (2 ** attempt)
                    time.sleep(backoff)
                    continue
                logger.error(
                    f"Peer {peer.node_id} ({peer.address}) unreachable after "
                    f"{RETRY_ATTEMPTS} attempts — removing",
                    self.node_id,
                )
                self._remove_peer_by_addr(peer.address)
                return False
            except requests.Timeout:
                if attempt < RETRY_ATTEMPTS - 1:
                    backoff = RETRY_BACKOFF * (2 ** attempt)
                    time.sleep(backoff)
                    continue
                logger.error(
                    f"Peer {peer.node_id} timed out after {RETRY_ATTEMPTS} attempts",
                    self.node_id,
                )
                return False
            except Exception as exc:
                logger.error(f"Send to {peer.address} failed: {exc}", self.node_id)
                return False

        return False

    def broadcast(self, message: Message, exclude_addr: Optional[str] = None) -> int:
        """
        Send *message* to all known peers (except *exclude_addr*) concurrently.

        Uses a ThreadPoolExecutor so sends happen in parallel rather than
        sequentially — much faster when many peers are connected.

        Returns the number of peers successfully reached.
        """
        peers = [p for p in self.get_peers() if p.address != exclude_addr]
        if not peers:
            return 0

        futures = {
            self._executor.submit(self.send_to_peer, p, message): p
            for p in peers
        }
        count = sum(
            1 for f in as_completed(futures) if f.result()
        )
        return count

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _advertised_host(self) -> str:
        """
        Return the host we advertise to peers.
        If binding on 0.0.0.0 we advertise 127.0.0.1 for same-machine peers.
        """
        if self.host in ("0.0.0.0", ""):
            return "127.0.0.1"
        return self.host

    def store_message(self, msg: Message) -> None:
        with self.messages_lock:
            self.messages[msg.id] = msg

    def remove_message(self, msg_id: str) -> Optional[Message]:
        with self.messages_lock:
            return self.messages.pop(msg_id, None)

    def get_messages(self) -> list[Message]:
        with self.messages_lock:
            return list(self.messages.values())
