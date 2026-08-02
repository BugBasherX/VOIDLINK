#!/usr/bin/env bash
# VOIDLINK — Wire up the three demo nodes after they are running.
#
# Creates this topology:
#   A ──── B ──── C
#    \          /
#     \────────/
#
# Usage (run while all three nodes are up):
#   bash scripts/connect_nodes.sh

set -euo pipefail

HOST="127.0.0.1"
PORT_A=5000
PORT_B=5001
PORT_C=5002

post() {
  local url="$1" body="$2"
  curl -s -X POST "$url" \
    -H "Content-Type: application/json" \
    -d "$body" \
    --max-time 5 || echo "  [WARN] Could not reach $url"
}

echo "Connecting VOIDLINK nodes..."
echo ""

# A → B
echo "  A → B  ($HOST:$PORT_A  ➜  $HOST:$PORT_B)"
post "http://$HOST:$PORT_A/api/hello" \
  "{\"node_id\":\"B\",\"host\":\"$HOST\",\"port\":$PORT_B}"

# B → A  (symmetric)
post "http://$HOST:$PORT_B/api/hello" \
  "{\"node_id\":\"A\",\"host\":\"$HOST\",\"port\":$PORT_A}"

# B → C
echo "  B → C  ($HOST:$PORT_B  ➜  $HOST:$PORT_C)"
post "http://$HOST:$PORT_B/api/hello" \
  "{\"node_id\":\"C\",\"host\":\"$HOST\",\"port\":$PORT_C}"

# C → B  (symmetric)
post "http://$HOST:$PORT_C/api/hello" \
  "{\"node_id\":\"B\",\"host\":\"$HOST\",\"port\":$PORT_B}"

# A → C  (direct cross-link)
echo "  A → C  ($HOST:$PORT_A  ➜  $HOST:$PORT_C)"
post "http://$HOST:$PORT_A/api/hello" \
  "{\"node_id\":\"C\",\"host\":\"$HOST\",\"port\":$PORT_C}"

# C → A  (symmetric)
post "http://$HOST:$PORT_C/api/hello" \
  "{\"node_id\":\"A\",\"host\":\"$HOST\",\"port\":$PORT_A}"

echo ""
echo "Done. Peer lists:"
echo "  Node A:  $(curl -s http://$HOST:$PORT_A/api/peers | python3 -c 'import sys,json; print([p["node_id"] for p in json.load(sys.stdin)])')"
echo "  Node B:  $(curl -s http://$HOST:$PORT_B/api/peers | python3 -c 'import sys,json; print([p["node_id"] for p in json.load(sys.stdin)])')"
echo "  Node C:  $(curl -s http://$HOST:$PORT_C/api/peers | python3 -c 'import sys,json; print([p["node_id"] for p in json.load(sys.stdin)])')"
echo ""
echo "Now go to any node terminal and type:"
echo "  /send Hello Network"
