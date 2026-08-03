# VOIDLINK v2

A CLI-based distributed P2P secure chat system. Every message is **AES-256-GCM encrypted** between peers and **Ed25519 signed** by the originator. Intermediate nodes re-encrypt for their peers — no eavesdropper on the wire can read messages, and forged/tampered messages are rejected.

## How to run

The configured workflow starts **Node A** on port 8000:

```
python node.py --id A --port 8000 --host 0.0.0.0
```

To run additional nodes (in separate shell tabs):

```
python node.py --id B --port 8001 --host 0.0.0.0
python node.py --id C --port 8002 --host 0.0.0.0
```

Connect them:

```
voidlink> /connect localhost:8001
voidlink> /connect localhost:8002
voidlink> /send Hello encrypted world!
```

## CLI commands

| Command | Description |
|---------|-------------|
| `/connect <host:port>` | Connect + ECDH key exchange |
| `/disconnect <host:port>` | Disconnect from a peer |
| `/send <message> [--ttl N]` | Broadcast a signed, encrypted message |
| `/peers` | List peers with encryption status + fingerprints |
| `/messages` | List messages with signature verification status |
| `/node` | Show this node's identity fingerprint + public key |
| `/stats` | Runtime stats (rejections, encryption status, etc.) |
| `/help` | Show all commands |
| `/quit` | Shutdown node |

## Security model

| Property | Mechanism |
|----------|-----------|
| **Transport confidentiality** | AES-256-GCM (per-peer session key) |
| **Key exchange** | X25519 ECDH on `/api/hello` handshake |
| **Message authenticity** | Ed25519 signature by originating node |
| **Tamper detection** | GCM authentication tag + Ed25519 verify |
| **Node identity** | Ed25519 keypair, fingerprint shown at startup |
| **Replay / loop prevention** | UUID dedup seen-set (existing) |

## Performance improvements

- **Concurrent broadcasts** via `ThreadPoolExecutor` (16 workers) — all peers reached in parallel
- **Connection pooling** via `requests.Session` with keep-alive (20 connections)
- **Exponential backoff retry** (3 attempts, 0.3 s base) before dropping an unreachable peer
- **Default TTL raised** from 10 s → 300 s (5 min) — far more useful for chat

## REST API (per node)

| Endpoint | Method | Payload |
|----------|--------|---------|
| `/api/hello` | POST | `{node_id, host, port, x25519_pub, ed25519_pub}` |
| `/api/bye` | POST | encrypted envelope |
| `/api/message` | POST | encrypted envelope `{enc, from}` |
| `/api/peers` | GET | — |
| `/api/healthz` | GET | — |

## Stack

- Python 3.12, Flask, requests, psutil, **cryptography** (new)

## User preferences

- Keep single-file-per-module structure
- OK with asyncio/websocket rewrite
- OK with web UI and SQLite persistence
- Growth directions: security/encryption ✓ done, smarter networking (gossip, async I/O), features (persistence, channels, file transfer)
