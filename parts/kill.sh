#!/usr/bin/env bash
set -euo pipefail

PORTS=(43001 5000 6006)

for p in "${PORTS[@]}"; do
  if ss -ltnp | grep -q ":$p "; then
    echo "killing listeners on TCP $p"
    fuser -k "${p}/tcp" >/dev/null 2>&1 || true
  fi
done

pkill -f "nc 127.0.0.1 43001" 2>/dev/null || true
pkill -f "arecord .* -r 16000" 2>/dev/null || true

echo "Done."

