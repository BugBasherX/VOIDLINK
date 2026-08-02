#!/usr/bin/env bash
# VOIDLINK — Send a test message to Node A and watch it propagate.
#
# Usage:
#   bash scripts/send_test.sh
#   bash scripts/send_test.sh "Custom message text" 30

set -euo pipefail

HOST="127.0.0.1"
PORT_A=5000
MSG="${1:-Hello VOIDLINK Network}"
TTL="${2:-10}"
UUID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
TS="$(python3 -c 'import time; print(time.time())')"

echo "Sending test message to Node A..."
echo "  Content : $MSG"
echo "  TTL     : ${TTL}s"
echo "  UUID    : $UUID"
echo ""

curl -s -X POST "http://$HOST:$PORT_A/api/message" \
  -H "Content-Type: application/json" \
  -d "{
    \"id\": \"$UUID\",
    \"sender_id\": \"CLI\",
    \"content\": \"$MSG\",
    \"timestamp\": $TS,
    \"ttl\": $TTL,
    \"hop_count\": 0
  }" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("Response:", d)'

echo ""
echo "Check each node terminal for [RECV] / [FWD] logs."
echo "Message will expire in ${TTL}s and show a [TTL] log."
