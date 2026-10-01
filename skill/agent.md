# HLS agent skill (short)

## Format (must match SFT / Luna trajectories)

Every model answer:

1. `<think>...</think>` — visible reasoning (not meta labels like "Implementation note")
2. Exactly one `<OUTPUT_CODE name="xxx.cpp">...</OUTPUT_CODE>` — full C++ source, no markdown fences

## Loop

1. Round 1: full task prompt (`initial_prompt.txt` style) → code
2. Run Vitis / HLS-Eval (csim → synth)
3. If fail: append feedback like trajectory attempt_02, ask for **complete** revised source
4. **Stop after at most 2 model calls** (1 generate + 1 repair). Keep best-so-far by stage.

## Feedback shape

```
Vitis HLS 2025.2 result: CSim=fail, Synthesis=skipped_csim_failed, failed_stage=csim.
Relevant tool output:
<truncated log>

Continue your solution in <think>: identify the error's cause, what you will change, and why the change should fix it. Then submit the revised COMPLETE source file. Do not edit the header, testbench, or task description.
```

## Do not

- Unlimited pi / bash agent loops
- Rewrite headers / testbenches
- Drop `<OUTPUT_CODE>` tags
