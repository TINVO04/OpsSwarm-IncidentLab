#!/usr/bin/env bash
set -euo pipefail
B=${BASE_URL:-http://localhost:8080}
curl -s -X POST $B/lab/reset >/dev/null
curl -s -X POST $B/lab/fault/C03 | python3 -m json.tool
D=$(curl -s -X POST $B/lab/detect)
echo "$D" | python3 -m json.tool
ID=$(python3 -c 'import json,sys;print(json.load(sys.stdin)["created"][0]["id"])' <<< "$D")
echo "Approving $ID"
curl -s -X POST $B/lab/approve/$ID | python3 -m json.tool
