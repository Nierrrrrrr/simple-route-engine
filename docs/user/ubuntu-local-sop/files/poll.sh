#!/usr/bin/env bash
set -euo pipefail
: "${SOP_HOME:?請先 source 本機 session.env}" "${API_BASE:?}"
ATTEMPT=$(cat "$SOP_HOME/last-request.txt")
EXECUTION_ID=$(cat "$ATTEMPT/execution-id.txt")
for ((i=0; i<180; i++)); do
  curl --fail-with-body --silent --show-error --config "$SOP_HOME/curl-auth.conf" \
    "$API_BASE/executions/$EXECUTION_ID" > "$ATTEMPT/state.json"
  jq '{executionId,state,permitHeld,routeVersion}' "$ATTEMPT/state.json"
  STATE=$(jq -er '.state' "$ATTEMPT/state.json")
  if [[ "$STATE" == SUCCEEDED ]]; then
    jq -e '.permitHeld == false' "$ATTEMPT/state.json"
    exit 0
  fi
  case "$STATE" in
    MANUAL_WAIT|RECONCILING|FAILED|CANCELLED)
      echo '需要查閱 incident 或外部 Job；請勿換 key 盲目重送。' >&2
      exit 1 ;;
  esac
  sleep 2
done
echo '超過本機觀察時間；execution 可能仍在執行，未取消任何工作。' >&2
exit 1
