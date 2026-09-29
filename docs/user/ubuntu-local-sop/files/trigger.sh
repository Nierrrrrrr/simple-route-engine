#!/usr/bin/env bash
set -euo pipefail
: "${SOP_HOME:?請先 source 本機 session.env}" "${API_BASE:?}"
BRANCH=${1:?用法: bash trigger.sh true 或 false}
[[ "$BRANCH" == true || "$BRANCH" == false ]] || { echo '只接受 true 或 false' >&2; exit 2; }
VERSION=$(jq -er '.version' "$SOP_HOME/published.json")
ATTEMPT="$SOP_HOME/requests/$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid)"
mkdir -p "$ATTEMPT"
printf '%s\n' "sop-$(cat /proc/sys/kernel/random/uuid)" > "$ATTEMPT/key.txt"
jq -n --argjson version "$VERSION" --argjson run "$BRANCH" \
 '{routeId:"ubuntu-rest-ansible-demo",routeVersion:$version,priority:"NORMAL",admissionMode:"QUEUE",input:{runAnsible:$run}}' \
 > "$ATTEMPT/body.json"
printf '%s\n' "$ATTEMPT" > "$SOP_HOME/last-request.txt"
printf '本次請求已保存在 %s\n' "$ATTEMPT"
curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
  -D "$ATTEMPT/headers.txt" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(cat "$ATTEMPT/key.txt")" \
  --data-binary "@$ATTEMPT/body.json" "$API_BASE/executions" > "$ATTEMPT/response.json"
jq . "$ATTEMPT/response.json"
jq -er '.executionId' "$ATTEMPT/response.json" > "$ATTEMPT/execution-id.txt"
