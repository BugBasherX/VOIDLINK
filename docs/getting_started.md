# VOIDLINK — Getting Started

## Prerequisites

- Python 3.11+
- pip / uv

## Install dependencies

```bash
cd voidlink
pip install -r requirements.txt
```

---

## Option 1 — Manual (three terminals)

Open three terminal windows and run one node in each:

```bash
# Terminal 1
python3 node.py --id A --port 5000

# Terminal 2
python3 node.py --id B --port 5001

# Terminal 3
python3 node.py --id C --port 5002
```

Then connect the nodes and send your first message:

```
# In Node A's terminal
voidlink> /connect localhost:5001
voidlink> /connect localhost:5002

# In Node B's terminal
voidlink> /connect localhost:5002

# Back in Node A
voidlink> /send Hello Network
```

Watch `[RECV]` and `[FWD]` logs appear on B and C in real time.
After 10 seconds, all nodes print `[TTL] Message … expired`.

---

## Option 2 — Automated demo script (tmux)

If you have `tmux` installed, one command does everything:

```bash
bash scripts/start_demo.sh
```

This opens three panes automatically. Then in a separate terminal:

```bash
bash scripts/connect_nodes.sh   # wire A↔B↔C↔A
bash scripts/send_test.sh       # inject a test message
```

---

## Option 3 — Docker Compose

```bash
docker compose up --build
```

Attach to any node:

```bash
docker attach voidlink-a    # Ctrl-P Ctrl-Q to detach
docker attach voidlink-b
docker attach voidlink-c
```

Then run `scripts/connect_nodes.sh` from the host to wire up the peers.

---

## Topology created

```
  A ──── B ──── C
   \          /
    \────────/
```

All three nodes see every message exactly once (duplicates are dropped).

---

## Next steps

- Read `docs/commands.md` for the full command reference.
- Read `docs/architecture.md` for how flooding and TTL work.
- Try `--latency` and `--loss` flags to simulate network conditions:

```bash
python3 node.py --id A --port 5000 --latency 300 --loss 20
```
