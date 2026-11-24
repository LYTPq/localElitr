#!/usr/bin/env bash
set -euo pipefail

PORTS=(43001 5000 6006 5001)

for p in "${PORTS[@]}"; do
  if ss -ltnp | grep -q ":$p "; then
    echo "killing listeners on TCP $p"
    fuser -k "${p}/tcp" >/dev/null 2>&1 || true
  fi
done

pkill -f "nc 127.0.0.1 43001" 2>/dev/null || true
pkill -f "arecord .* -r 16000" 2>/dev/null || true


pkill -f "lang_manager.py" 2>/dev/null || true
pkill -f "mtwrapper.py" 2>/dev/null || true
pkill -f "ct2_client.py" 2>/dev/null || true
pkill -f "online-text-flow client" 2>/dev/null || true

echo "Done."
