#!/usr/bin/env bash
set -euo pipefail
: "${SOP_HOME:?請先 source 本機 session.env}"
source "$SOP_HOME/app.env"
read -r -s -p 'MariaDB 應用程式帳號密碼: ' ROUTE_DB_PASSWORD
printf '\n'
export ROUTE_DB_PASSWORD
cd "$PROJECT_DIR"
exec java -jar target/route-engine-0.1.0.jar
