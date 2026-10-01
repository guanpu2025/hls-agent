#!/usr/bin/env bash
# Initial HLS harness launcher (laptop side).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

export HLS_EVAL_ROOT="${HLS_EVAL_ROOT:-/data/guanpu/hls-eval}"
export XILINX_VIVADO="${XILINX_VIVADO:-/data/guanpu/Xilinx/2025.2/Vivado}"
export XILINX_VITIS="${XILINX_VITIS:-/data/guanpu/Xilinx/2025.2/Vitis}"
export PATH="$XILINX_VITIS/bin:$XILINX_VIVADO/bin:${PATH:-}"
export HLS_API_BASE="${HLS_API_BASE:-http://192.168.0.157:8731/v1}"
export HLS_MODEL="${HLS_MODEL:-halogen-qwen3.8-flash-next}"
export HLS_FPGA_PART="${HLS_FPGA_PART:-xczu3eg-sbva484-1-e}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,192.168.0.157"
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost,192.168.0.157"
export PYTHONPATH="$HLS_EVAL_ROOT:${PYTHONPATH:-}"

PY="${HLS_EVAL_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

exec env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
  "$PY" "$ROOT/run_harness.py" "$@"
