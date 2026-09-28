#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
[[ $# == 2 ]] || { echo 'Usage: verify-phase.sh PHASE EVIDENCE_DIR' >&2; exit 2; }
[[ "${ROUTE_SOURCE_FINGERPRINT:-}" =~ ^[a-f0-9]{64}$ ]] || { echo 'Missing/invalid injected ROUTE_SOURCE_FINGERPRINT' >&2; exit 2; }
case "$1" in
 M0) exec python3 -B scripts/m0_validate.py "$2" ;;
 M1) exec python3 -B scripts/foundation_gate.py "$2" ;;
 M2) exec python3 -B scripts/admission_gate.py "$2" ;;
 M3) exec python3 -B scripts/engine_gate.py "$2" ;;
 M4) exec python3 -B scripts/adapter_gate.py "$2" ;;
 M5) exec python3 -B scripts/recovery_gate.py "$2" ;;
 M6) exec python3 -B scripts/hardening_gate.py "$2" ;;
 FINAL) exec python3 -B scripts/final_gate.py "$2" ;;
 *) echo "Unknown phase: $1" >&2; exit 2 ;;
esac
