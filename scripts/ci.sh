#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ROUTE_RUN_ID:?Set unique isolated run ID}"
export PYTHONDONTWRITEBYTECODE=1
source scripts/env.sh
bash scripts/verify-desktop-phase.sh FINAL ".evidence/desktop/$ROUTE_RUN_ID/FINAL/ci"
