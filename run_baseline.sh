#!/usr/bin/env bash
# Convenience wrappers (same as python3 run_*.py)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export HLS_API_BASE="${HLS_API_BASE:-http://127.0.0.1:18731/v1}"
export HLS_MODEL="${HLS_MODEL:-halogen-qwen3.8-flash-next}"
# Prefer SSH tunnel (ssh -L 18731:127.0.0.1:8731 evo-x2). Direct LAN POST is flaky with local proxies.
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,192.168.0.157"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost,192.168.0.157"
exec env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
  python3 "$ROOT/run_baseline.py" "$@"
