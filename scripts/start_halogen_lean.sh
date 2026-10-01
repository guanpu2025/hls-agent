#!/usr/bin/env bash
# Start lean halogen-flash-server on EVO-X2 for HLS smoke / short prompts.
# Run ON the EVO host (aup@192.168.0.157).
set -euo pipefail

NAME="${HALOGEN_NAME:-halogen-smoke}"
IMG="${HALOGEN_IMAGE:-ghcr.io/peonist-ai/halogen-flash-server:0.15.1}"
MODELS="${HALOGEN_MODELS:-/home/aup/halogen-models}"

# Lean defaults: small KV frees RAM for weight file-cache (PIN=0).
# Large KV + desktop apps causes multi-minute full-CPU stalls with no log output.
export HALOGEN_CTX="${HALOGEN_CTX:-8192}"
export HALOGEN_KV_POOL_POSITIONS="${HALOGEN_KV_POOL_POSITIONS:-8192}"
export HALOGEN_KV_SLOTS="${HALOGEN_KV_SLOTS:-1}"
export HALOGEN_MAX_TOK="${HALOGEN_MAX_TOK:-128}"
export HALOGEN_FLASH_PIN_TRUNK="${HALOGEN_FLASH_PIN_TRUNK:-0}"
export HALOGEN_ENGINE_WATCHDOG_S="${HALOGEN_ENGINE_WATCHDOG_S:-0}"
export HALOGEN_HOST_RESERVE_GIB="${HALOGEN_HOST_RESERVE_GIB:-8}"
export HALOGEN_CK_OVERLAY="${HALOGEN_CK_OVERLAY:-none}"
export HALOGEN_PROMPT_CACHE="${HALOGEN_PROMPT_CACHE:-0}"
export HALOGEN_ENABLE_THINKING="${HALOGEN_ENABLE_THINKING:-0}"

tmux kill-session -t halogen 2>/dev/null || true
podman rm -f "$NAME" 2>/dev/null || true
podman ps -q --filter ancestor="$IMG" | xargs -r podman kill
sleep 2

tmux new-session -d -s halogen "podman run --rm --name $NAME -p 8731:8731 \
  --device /dev/kfd --device /dev/dri --group-add keep-groups --ipc=host \
  --ulimit memlock=-1:-1 \
  -v $MODELS:/models:ro \
  -v $MODELS/tokenizer:/tokenizer:ro \
  -e HALOGEN_CTX -e HALOGEN_KV_POOL_POSITIONS -e HALOGEN_KV_SLOTS \
  -e HALOGEN_MAX_TOK -e HALOGEN_FLASH_PIN_TRUNK -e HALOGEN_ENGINE_WATCHDOG_S \
  -e HALOGEN_HOST_RESERVE_GIB -e HALOGEN_CK_OVERLAY -e HALOGEN_PROMPT_CACHE \
  -e HALOGEN_ENABLE_THINKING \
  $IMG 2>&1 | tee /tmp/halogen-smoke.log"

echo "waiting for /v1/models ..."
for i in $(seq 1 60); do
  if curl -sS -m 2 http://127.0.0.1:8731/v1/models 2>/dev/null | grep -q halogen; then
    echo "READY"
    exit 0
  fi
  sleep 2
done
echo "FAILED to become ready; see /tmp/halogen-smoke.log" >&2
exit 1
