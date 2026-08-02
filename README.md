# VOIDLINK

A CLI-only distributed messaging system demonstrating peer-to-peer communication, message propagation, and ephemeral messaging using Python and Flask.

```
 __   ___  ___ ____  _     ___ _   _ _  __
 \ \ / / |/ _ \_ _|| |   |_ _| \ | | |/ /
  \ V /| | | | || | | |    | ||  \| | ' /
   \_/ |_|\___/|___||_|   |___|_|\__|_|\_\
```

---

## Architecture Diagram

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                    VOIDLINK Node Internals                       │
 │                                                                  │
 │   stdin ──► CLIHandler ──► VoidlinkNode                         │
 │                                │                                 │
 │                    ┌───────────┴───────────┐                    │
 │                    ▼                       ▼                     │
 │            NetworkManager           RoutingTable                 │
 │          (Flask HTTP server)      (seen_messages set)            │
 │          ┌──────────────┐         ┌──────────────┐              │
 │          │  /api/hello  │         │  process()   │              │
 │          │  /api/bye    │◄───────►│  flood()     │              │
 │          │  /api/message│         └──────────────┘              │
 │          │  /api/peers  │                                        │
 │          └──────────────┘                                        │
 │                    │                                             │
 │                    ▼                                             │
 │             TTLManager (background thread)                       │
 │             scans message store every 1 s                        │
 │             expires messages past their TTL                      │
 └─────────────────────────────────────────────────────────────────┘

 Node-to-Node Communication (flooding):

  ┌────┐  POST /api/message  ┌────┐  POST /api/message  ┌────┐
  │ A  │────────────────────►│ B  │────────────────────►│ C  │
  └────┘                     └────┘                     └────┘
    │                          │
    └──────────────────────────┘
    POST /api/message (direct connection A→C also possible)

 Duplicate messages (same UUID) are silently dropped by each node's
 RoutingTable, preventing infinite loops.
```

---

## Folder Structure

```
voidlink/
├── node.py              Entry point — wires all subsystems, starts CLI
├── network.py           Flask HTTP server, peer registry, outbound sends
├── peer.py              Peer data class (node_id, host, port)
├── message.py           Message data class (UUID, TTL, hop_count, …)
├── ttl.py               Background TTL expiry janitor thread
├── routing.py           Flood routing with loop prevention (seen_messages)
├── cli.py               CLI command parser and dispatcher
├── config.py            Configuration defaults and constants
├── logger.py            Coloured ANSI terminal logging
├── utils.py             Utility helpers (parse_addr, human_uptime, …)
│
├── scripts/
│   ├── start_demo.sh    Launch three nodes in tmux / gnome-terminal
│   ├── connect_nodes.sh Wire up A↔B↔C↔A via curl
│   └── send_test.sh     Inject a test message via curl
│
├── docs/
│   ├── getting_started.md  Install + three startup options
│   ├── commands.md         Full CLI command reference
│   ├── architecture.md     Internals, threading, REST API, algorithms
│   └── cross_network.md    Connect nodes across different networks
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Requirements

- Python 3.11+
- `pip install -r requirements.txt`

```
flask>=3.0.0
requests>=2.31.0
psutil>=5.9.0
```

---

## Quick Start

See **`docs/getting_started.md`** for full instructions.

### Option 1 — Manual (three terminals)

```bash
# Terminal 1               Terminal 2               Terminal 3
python3 node.py            python3 node.py           python3 node.py
  --id A --port 5000         --id B --port 5001        --id C --port 5002
```

Then in Node A:
```
voidlink> /connect localhost:5001
voidlink> /connect localhost:5002
voidlink> /send Hello Network
```

### Option 2 — Automated (requires tmux)

```bash
bash scripts/start_demo.sh    # opens three panes
bash scripts/connect_nodes.sh # wires A↔B↔C↔A
bash scripts/send_test.sh     # injects a test message
```

### Option 3 — Docker Compose

```bash
docker compose up --build
docker attach voidlink-a      # Ctrl-P Ctrl-Q to detach
```

---

## Topology

```
  A ──── B ──── C
   \          /
    \────────/
```

- **Node A**: `[SEND]  Sent message 4af9e1b2 to 2 peer(s)`
- **Node B**: `[RECV]  Message 4af9e1b2 from A via 127.0.0.1:5000 (hop 1, 9.7s left)`
- **Node C**: `[RECV]  Message 4af9e1b2 from A (direct, hop 1) — duplicate from B silently dropped`

After 10 s: `[TTL]  Message 4af9e1b2… expired and deleted from memory`

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/send <message> [--ttl <sec>]` | Broadcast a message to the network |
| `/connect <host:port>` | Connect to a peer node |
| `/disconnect <host:port>` | Disconnect from a peer node |
| `/peers` | List all currently connected peers |
| `/messages` | List all messages currently in memory |
| `/node` | Show this node's ID and listen address |
| `/stats` | Show runtime statistics (sent, received, forwarded, expired, uptime, memory) |
| `/clear` | Clear the terminal screen |
| `/quit` | Shut down this node gracefully |

### Adjustable TTL

```
voidlink> /send Important announcement --ttl 60
```

---

## Message Fields

Each message carries:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Globally unique identifier (used for deduplication) |
| `sender_id` | string | Node ID of the original sender |
| `content` | string | Human-readable payload |
| `timestamp` | float | Unix time of creation |
| `ttl` | int | Seconds until expiry (from creation time) |
| `hop_count` | int | Number of forwarding hops so far |

---

## Routing: Flood with Loop Prevention

Each node maintains an in-memory `seen_messages` set of UUID strings.

When a message arrives:
1. If the UUID is in `seen_messages` → **drop silently** (loop prevention)
2. Otherwise:
   - Add UUID to `seen_messages`
   - Store message locally
   - **Flood**: POST to all known peers except the sender
   - Increment `hop_count` on the forwarded copy

A hard cap of `MAX_HOPS = 20` prevents runaway propagation in unexpected topologies.

---

## Networking Protocol

REST over HTTP (Flask). All payloads are JSON.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/hello` | POST | Peer announces itself (connect handshake) |
| `/api/bye` | POST | Peer announces disconnect |
| `/api/message` | POST | Receive a propagated message |
| `/api/peers` | GET | List known peers (diagnostic) |
| `/api/healthz` | GET | Liveness probe |

---

## Concepts Demonstrated

| Concept | Where |
|---------|-------|
| Distributed systems | Multiple independent nodes, no central coordinator |
| Peer-to-peer communication | Direct HTTP POST between nodes |
| Message propagation | Flood routing in `routing.py` |
| Ephemeral messaging | TTL expiry in `ttl.py` |
| Loop prevention | `seen_messages` set in `RoutingTable` |
| Concurrency | Flask threaded server + background TTL thread |
| Type hints | All modules use full PEP 484 annotations |

---

## Configuration (`config.py`)

| Constant | Default | Description |
|----------|---------|-------------|
| `DEFAULT_TTL` | `10` | Seconds before a message expires |
| `MAX_HOPS` | `20` | Hard cap on hop count |
| `REQUEST_TIMEOUT` | `3` | HTTP request timeout (seconds) |
| `MESSAGE_CHECK_INTERVAL` | `1.0` | TTL janitor interval (seconds) |

---

## Stretch Goal Pointers

The codebase is designed to be extended:

- **Adjustable TTL**: already supported via `/send --ttl <seconds>`
- **Message priorities**: add a `priority` field to `Message` and sort the peer queue
- **Network latency simulation**: add `time.sleep(random.uniform(...))` in `NetworkManager.send_to_peer`
- **Packet loss simulation**: add a random drop in the same method
- **AES encryption**: encrypt `message.content` before `to_dict()` / after `from_dict()`
- **Docker Compose**: one service per node, environment variables for `--id` and `--port`
