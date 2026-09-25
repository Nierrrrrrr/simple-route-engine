#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
: "${ROUTE_DB_URL:?Set isolated database URL}"
: "${ROUTE_DB_USER:?Set database user}"
: "${ROUTE_DB_PASSWORD:?Set database password}"
: "${ROUTE_ADMIN_TOKEN_SHA256:?Set high entropy bearer token SHA-256}"
exec "$JAVA_HOME/bin/java" -Duser.timezone=UTC -jar target/route-engine-0.1.0.jar
