#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
export PYTHONDONTWRITEBYTECODE=1
exec python3 -B scripts/doctor.py "$@"
