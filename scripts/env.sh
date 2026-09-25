#!/usr/bin/env bash
ROUTE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export JAVA_HOME="$ROUTE_ROOT/.tools/java"
export PATH="$JAVA_HOME/bin:$ROUTE_ROOT/.tools/maven/bin:$ROUTE_ROOT/.tools/bin:$PATH"
export MAVEN_USER_HOME="$ROUTE_ROOT/.cache/maven"
export MAVEN_OPTS="-Dmaven.repo.local=$ROUTE_ROOT/.cache/m2"
# Explicit test environment only. Never inherit a user's production context/config.
: "${ROUTE_RUN_ID:?Set ROUTE_RUN_ID to the desktop run identifier}"
[[ "$ROUTE_RUN_ID" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,49}$ ]] || { echo 'Invalid run id' >&2; return 2; }
export ROUTE_RUN_ROOT="$ROUTE_ROOT/.evidence/desktop/$ROUTE_RUN_ID"
mkdir -p "$ROUTE_RUN_ROOT/docker-config"
export DOCKER_CONFIG="$ROUTE_RUN_ROOT/docker-config"
export DOCKER_HOST=unix:///var/run/docker.sock
unset DOCKER_CONTEXT
export KUBECONFIG="$ROUTE_RUN_ROOT/kubeconfig"
export ROUTE_CLUSTER="re-${ROUTE_RUN_ID,,}"
