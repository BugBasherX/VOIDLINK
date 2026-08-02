# VOIDLINK — Architecture

## Overview

VOIDLINK is a fully decentralised, serverless messaging system. There is no
broker, no coordinator, and no shared state — each node is equal. Nodes
discover each other only through explicit `/connect` commands or peer
handshakes; there is no automatic discovery.

---

## ASCII Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                       VOIDLINK Node Internals                        │
│                                                                      │
│  stdin ──► CLIHandler ──────────────────────► VoidlinkNode           │
│                                                     │                │
│                              ┌──────────────────────┴──────────┐    │
│                              │                                  │    │
│                       NetworkManager                     RoutingTable│
│                    ┌─────────────────┐              ┌──────────────┐ │
│                    │ Flask HTTP srv  │◄────────────►│ seen_messages│ │
│                    │  /api/hello     │              │    (set)     │ │
│                    │  /api/bye       │              │  process()   │ │
│                    │  /api/message   │              │  flood()     │ │
│                    │  /api/peers     │              └──────────────┘ │
│                    │  /api/healthz   │                               │
│                    └────────┬────────┘                               │
│                             │                                        │
│                    TTLManager (background thread)                    │
│                    scans messages every 1 s                          │
│                    expires + prunes seen_messages                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Node-to-Node Communication

```
  POST /api/message   POST /api/message
┌────┐ ──────────► ┌────┐ ──────────► ┌────┐
│ A  │             │ B  │             │ C  │
└────┘ ◄────────── └────┘ ◄────────── └────┘
        /api/hello        /api/hello

  A → B direct link:  POST http://B:5001/api/hello  (body: A's id+addr)
  B stores A as peer, optionally reciprocates
```

All payloads are JSON over plain HTTP. No persistent connections — each
message is a single HTTP POST.

---

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `node.py` | Top-level coordinator; wires subsystems; runs CLI |
| `network.py` | Flask HTTP server; peer registry; outbound HTTP sends |
| `routing.py` | Deduplication (`seen_messages`); flood forwarding |
| `ttl.py` | Background janitor; expires messages; prunes seen-set |
| `message.py` | Immutable message dataclass; serialisation; TTL math |
| `peer.py` | Peer dataclass; endpoint URL construction |
| `cli.py` | Command parser; all `/command` handlers |
| `config.py` | Constants and defaults |
| `logger.py` | Coloured ANSI terminal output |
| `utils.py` | Shared helpers (addr parsing, formatting) |

---

## Routing Algorithm — Flood with Loop Prevention

```
Message arrives at node N
        │
        ▼
  UUID in seen_messages?
   YES ──► drop silently (duplicate)
   NO  ──► add UUID to seen_messages
           store message locally
           log [RECV]
           hop_count > MAX_HOPS?
             YES ──► drop
             NO  ──► increment hop_count
                     POST to all peers except sender
                     log [FWD]
```

`seen_messages` is pruned by TTLManager when the corresponding message
expires, so the set never grows unbounded.

---

## Message Lifecycle

```
  [Created]              [In-flight]             [Expired]
     │                       │                       │
  sender                  each hop              TTL janitor
  node.py              routing.py              ttl.py
  Message.create()     process()               _expire_messages()
     │                       │                       │
     ▼                       ▼                       ▼
  UUID assigned        seen_messages check      remove from store
  timestamp set        store + forward          remove from seen set
  hop_count = 0        hop_count + 1            log [TTL]
```

---

## Threading Model

| Thread | Name | Role |
|--------|------|------|
| Main | `MainThread` | CLI `input()` loop |
| Flask | `flask-<id>` | HTTP server (threaded mode, one thread per request) |
| TTL janitor | `ttl-<id>` | Message expiry checker (daemon) |

All shared state (peer registry, message store, seen-set) is protected by
`threading.Lock` / `threading.RLock`. The Flask server uses its own internal
thread pool for concurrent request handling.

---

## Network Simulation

Pass flags to `node.py` to simulate adverse network conditions:

```bash
python3 node.py --id A --port 5000 --latency 200 --loss 15
```

| Flag | Effect | Implementation |
|------|--------|---------------|
| `--latency <ms>` | Delays every outbound POST by N ms | `time.sleep(ms/1000)` in `send_to_peer` |
| `--loss <pct>` | Randomly drops N% of outbound messages | `random.uniform(0,100) < pct` check |

Both flags default to 0 (disabled). They are local — each node can have
different simulation parameters, modelling asymmetric network paths.

---

## REST API Reference

All endpoints accept and return JSON.

### `GET /api/healthz`
Liveness probe.
```json
{ "status": "ok", "node_id": "A" }
```

### `POST /api/hello`
Peer announces itself. Registers the sender as a known peer.
```json
// Request
{ "node_id": "B", "host": "127.0.0.1", "port": 5001 }
// Response
{ "node_id": "A", "status": "ok" }
```

### `POST /api/bye`
Peer announces disconnect. Removes the sender from the peer registry.
```json
// Request
{ "host": "127.0.0.1", "port": 5001 }
// Response
{ "status": "ok" }
```

### `POST /api/message`
Receive a propagated message.
```json
// Request
{
  "id": "uuid-string",
  "sender_id": "A",
  "content": "Hello Network",
  "timestamp": 1720000000.0,
  "ttl": 10,
  "hop_count": 1,
  "_source_addr": "127.0.0.1:5000"
}
// Response
{ "status": "ok" }
```

### `GET /api/peers`
List all currently known peers.
```json
[
  { "node_id": "B", "host": "127.0.0.1", "port": 5001 },
  { "node_id": "C", "host": "127.0.0.1", "port": 5002 }
]
```
