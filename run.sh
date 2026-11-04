#!/bin/sh
# TAIG Helm — dev runner. Localhost only.
set -eu
cd "$(dirname "$0")"
if [ ! -f config.json ] && [ "${HELM_MOCK:-}" != "1" ]; then
  echo "config.json missing — copy config.example.json to config.json first, or run HELM_MOCK=1 ./run.sh for a mock demo."
  exit 1
fi
exec python3 server.py
