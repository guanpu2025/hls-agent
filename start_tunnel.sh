#!/usr/bin/env bash
# Keep an SSH tunnel: laptop:18731 -> EVO-X2:8731
set -euo pipefail
KEY="${HOME}/.ssh/id_ed25519_evox2"
HOST="${EVO_HOST:-aup@192.168.0.157}"
PORT_LOCAL="${HLS_TUNNEL_PORT:-18731}"

if ss -ltn | grep -q ":${PORT_LOCAL} "; then
  echo "tunnel already listening on ${PORT_LOCAL}"
  exit 0
fi

ssh -f -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -i "$KEY" -o IdentitiesOnly=yes \
  -L "${PORT_LOCAL}:127.0.0.1:8731" "$HOST"
echo "tunnel up: http://127.0.0.1:${PORT_LOCAL}/v1"
