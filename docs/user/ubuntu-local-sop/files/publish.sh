#!/usr/bin/env bash
set -euo pipefail
: "${SOP_HOME:?請先 source 本機 session.env}"
: "${PROJECT_DIR:?}" "${API_BASE:?}"
AUTH=(--config "$SOP_HOME/curl-auth.conf")
FILES="$PROJECT_DIR/docs/user/ubuntu-local-sop/files"
curl --fail-with-body --silent --show-error "${AUTH[@]}" \
  -H 'Content-Type: application/json' -d \
  '{"routeId":"ubuntu-rest-ansible-demo","name":"Ubuntu REST / Ansible 範例"}' \
  "$API_BASE/routes" > "$SOP_HOME/route-created.json"
jq '{definition:.}' "$FILES/example-route.json" > "$SOP_HOME/draft-body.json"
curl --fail-with-body --silent --show-error "${AUTH[@]}" \
  -H 'Content-Type: application/json' --data-binary "@$SOP_HOME/draft-body.json" \
  "$API_BASE/routes/ubuntu-rest-ansible-demo/versions" > "$SOP_HOME/draft.json"
VERSION=$(jq -er '.version' "$SOP_HOME/draft.json")
jq -e '{stateVersion:.stateVersion}' "$SOP_HOME/draft.json" > "$SOP_HOME/publish-body.json"
curl --fail-with-body --silent --show-error "${AUTH[@]}" \
  -H 'Content-Type: application/json' --data-binary "@$SOP_HOME/publish-body.json" \
  "$API_BASE/routes/ubuntu-rest-ansible-demo/versions/$VERSION/publish" \
  > "$SOP_HOME/published.json"
jq -e '.status == "PUBLISHED"' "$SOP_HOME/published.json"
jq '{routeId,version,status,stateVersion,definitionHash}' "$SOP_HOME/published.json"
