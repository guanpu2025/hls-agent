# HLS two-step harness (baseline vs repair)

Minimal OpenAI-compatible client for the lab halogen server, aligned with Luna trajectory format (`<think>` + `<OUTPUT_CODE>`).

## API (lab EVO-X2)

```bash
export HLS_API_BASE=http://192.168.0.157:8731/v1
export HLS_MODEL=halogen-qwen3.8-flash-next
```

Keep the server running in tmux on the mini PC.

## Commands

```bash
cd /data/guanpu/hls-agent

# Single shot (competition-style baseline)
python3 run_baseline.py --prompt /path/to/initial_prompt.txt --out outputs/baseline

# Two-step: generate, then repair if --feedback is given (max 2 model calls)
python3 run.py --prompt /path/to/initial_prompt.txt --out outputs/agent
python3 run.py --prompt /path/to/initial_prompt.txt \
  --feedback /path/to/vitis_feedback.txt --out outputs/agent_repair

# Smoke test against live API using a trajectory prompt
python3 run_baseline.py \
  --prompt /data/guanpu/HLS/luna-trajectories/2026-09-25/luna6_add_round_key_smoke_20260925_v2/initial_prompt.txt \
  --out outputs/smoke_add_round_key
```

Vitis / HLS-Eval wiring comes next: pass tool stderr into `--feedback` (same text shape as trajectory `attempt_02` prompts).
