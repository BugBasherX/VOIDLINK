#!/usr/bin/env bash
# VOIDLINK — Start a three-node demo in separate terminal tabs/panes.
#
# Requires one of:
#   tmux  — recommended (splits the window into three panes automatically)
#   gnome-terminal / xterm / kitty / alacritty — opens three windows
#
# Usage:
#   bash scripts/start_demo.sh
#   bash scripts/start_demo.sh --latency 100 --loss 10   # with simulation

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

EXTRA_ARGS="${*:-}"   # forward any extra flags (e.g. --latency 200 --loss 20)

# ── tmux (preferred) ─────────────────────────────────────────────────────────
if command -v tmux &>/dev/null; then
  SESSION="voidlink"
  tmux new-session  -d -s "$SESSION" -x 220 -y 50 \
    "cd '$ROOT' && python3 node.py --id A --port 5000 $EXTRA_ARGS; exec bash"

  tmux split-window -h -t "$SESSION" \
    "cd '$ROOT' && python3 node.py --id B --port 5001 $EXTRA_ARGS; exec bash"

  tmux split-window -v -t "$SESSION":0.0 \
    "cd '$ROOT' && python3 node.py --id C --port 5002 $EXTRA_ARGS; exec bash"

  tmux select-layout -t "$SESSION" tiled
  echo "Three VOIDLINK nodes started in tmux session '$SESSION'."
  echo "Attach with:  tmux attach -t $SESSION"
  echo ""
  echo "Once attached, connect the nodes with:"
  echo "  bash scripts/connect_nodes.sh"
  tmux attach -t "$SESSION"

# ── gnome-terminal ────────────────────────────────────────────────────────────
elif command -v gnome-terminal &>/dev/null; then
  gnome-terminal -- bash -c "cd '$ROOT' && python3 node.py --id A --port 5000 $EXTRA_ARGS; exec bash" &
  gnome-terminal -- bash -c "cd '$ROOT' && python3 node.py --id B --port 5001 $EXTRA_ARGS; exec bash" &
  gnome-terminal -- bash -c "cd '$ROOT' && python3 node.py --id C --port 5002 $EXTRA_ARGS; exec bash" &
  echo "Three VOIDLINK nodes started in gnome-terminal windows."

# ── xterm fallback ────────────────────────────────────────────────────────────
elif command -v xterm &>/dev/null; then
  xterm -title "VOIDLINK Node A" -e "cd '$ROOT' && python3 node.py --id A --port 5000 $EXTRA_ARGS; bash" &
  xterm -title "VOIDLINK Node B" -e "cd '$ROOT' && python3 node.py --id B --port 5001 $EXTRA_ARGS; bash" &
  xterm -title "VOIDLINK Node C" -e "cd '$ROOT' && python3 node.py --id C --port 5002 $EXTRA_ARGS; bash" &
  echo "Three VOIDLINK nodes started in xterm windows."

else
  echo "No supported terminal multiplexer found."
  echo "Please open three terminals manually and run:"
  echo ""
  echo "  Terminal 1:  cd '$ROOT' && python3 node.py --id A --port 5000 $EXTRA_ARGS"
  echo "  Terminal 2:  cd '$ROOT' && python3 node.py --id B --port 5001 $EXTRA_ARGS"
  echo "  Terminal 3:  cd '$ROOT' && python3 node.py --id C --port 5002 $EXTRA_ARGS"
  exit 1
fi
