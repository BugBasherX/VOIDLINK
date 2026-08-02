# VOIDLINK — CLI Command Reference

All commands are entered at the `voidlink> ` prompt and must start with `/`.

---

## `/help`
Print the full command list.

```
voidlink> /help
```

---

## `/send <message> [--ttl <seconds>]`
Create and broadcast a new message to all connected peers.

```
voidlink> /send Hello Network
voidlink> /send Urgent notice --ttl 60
voidlink> /send Short-lived ping --ttl 3
```

- Default TTL is **10 seconds**.
- The message propagates via flooding — every peer forwards it to their
  peers, and so on, until all reachable nodes have seen it.
- Duplicate copies (same UUID) are silently dropped by each node.

**Output on sender (Node A):**
```
[SEND]  Sent message 4af9e1b2 to 2 peer(s) | ttl=10s | "Hello Network"
```

**Output on receiving nodes (B, C):**
```
[RECV]  Message 4af9e1b2 from A via 127.0.0.1:5000 (hop 1, 9.8s left)
```

**After TTL expires (all nodes):**
```
[TTL]   Message 4af9e1b2… expired and deleted from memory
```

---

## `/connect <host:port>`
Connect to a remote peer node.

```
voidlink> /connect localhost:5001
voidlink> /connect 192.168.1.10:5000
```

- Sends a handshake (`POST /api/hello`) to the remote node.
- Both nodes register each other as peers.
- Connection is in-memory only — it does not persist after `/quit`.

**Output:**
```
[INFO]  Connecting to localhost:5001…
[PEER]  Connected to Node B at localhost:5001
```

---

## `/disconnect <host:port>`
Gracefully disconnect from a peer.

```
voidlink> /disconnect localhost:5001
```

- Notifies the remote peer via `POST /api/bye`.
- Removes the peer from the local registry.

**Output:**
```
[PEER]  Disconnected from Node B (localhost:5001)
```

---

## `/peers`
List all currently connected peers.

```
voidlink> /peers
```

**Output:**
```
[CMD]   Connected peers (2):
[CMD]     • B          127.0.0.1:5001
[CMD]     • C          127.0.0.1:5002
```

---

## `/messages`
List all messages currently in memory (not yet expired).

```
voidlink> /messages
```

**Output:**
```
[CMD]   In-memory messages (2):
[CMD]     [4af9e1b2] from=A hops=0 ttl=7.3s  "Hello Network"
[CMD]     [c3d7a120] from=B hops=1 ttl=2.1s  "Another message"
```

---

## `/node`
Show this node's ID and listen address.

```
voidlink> /node
```

**Output:**
```
[CMD]   Node ID: A  |  Listening: 127.0.0.1:5000
```

---

## `/stats`
Show full runtime statistics.

```
voidlink> /stats
```

**Output:**
```
[STAT]  ── Node Statistics ─────────────────────
[STAT]    Node ID                A
[STAT]    Listen address         127.0.0.1:5000
[STAT]    Connected peers        2
[STAT]    Messages in memory     1
[STAT]    Messages sent          3
[STAT]    Messages received      5
[STAT]    Messages forwarded     8
[STAT]    Messages expired       4
[STAT]    Uptime                 2m 14s
[STAT]    Memory usage           18.3 MB
[STAT]    Sim latency            off
[STAT]    Sim packet loss        off
[STAT]  ────────────────────────────────────────
```

---

## `/clear`
Clear the terminal screen.

```
voidlink> /clear
```

---

## `/quit`
Gracefully shut down this node.

```
voidlink> /quit
```

- Notifies all connected peers via `POST /api/bye`.
- Stops the TTL janitor thread.
- Exits the process.

---

## Node Startup Flags

```
python3 node.py --id <ID> --port <PORT> [--host <HOST>] [--latency <MS>] [--loss <PCT>]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--id` | *(required)* | Unique node identifier (e.g. `A`, `NodeAlpha`) |
| `--port` | `5000` | TCP port to listen on |
| `--host` | `0.0.0.0` | Interface to bind (use `0.0.0.0` for all interfaces) |
| `--latency` | `0` | Artificial send delay in milliseconds |
| `--loss` | `0` | Simulated packet-loss percentage (0–100) |

**Examples:**
```bash
# Basic node
python3 node.py --id A --port 5000

# Node with 200 ms latency and 10% packet loss
python3 node.py --id B --port 5001 --latency 200 --loss 10

# Node bound to a specific interface
python3 node.py --id C --port 5002 --host 192.168.1.5
```
