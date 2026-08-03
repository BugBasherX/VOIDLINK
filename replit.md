# VOIDLINK

A CLI-only distributed P2P messaging system demonstrating peer-to-peer communication, message propagation, flood routing, and ephemeral TTL-based messaging. Written in Python with Flask as the inter-node HTTP transport.

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

Then wire them together from the CLI:

```
/connect localhost:8001
/send Hello Network
/peers
/stats
/quit
```

## CLI commands

| Command | Description |
|---------|-------------|
| `/connect <host:port>` | Connect to another node |
| `/disconnect <host:port>` | Disconnect from a peer |
| `/send <message> [--ttl N]` | Broadcast a message (default TTL: 10s) |
| `/peers` | List connected peers |
| `/messages` | List received messages |
| `/stats` | Show node statistics |
| `/help` | Show all commands |
| `/quit` | Shutdown the node |

## REST API (per node)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hello` | POST | Peer connect handshake |
| `/api/bye` | POST | Peer disconnect |
| `/api/message` | POST | Receive a propagated message |
| `/api/peers` | GET | List known peers |
| `/api/healthz` | GET | Liveness probe |

## Stack

- Python 3.12
- Flask (inter-node HTTP server)
- requests (outbound peer calls)
- psutil (system stats)

## Dependencies

```
pip install -r requirements.txt
```

## User preferences

- Keep single-file-per-module structure
- OK with asyncio/websocket rewrite
- OK with web UI and SQLite persistence
- Growth directions: security/encryption, smarter networking (gossip, async I/O), features (persistence, channels, file transfer)
