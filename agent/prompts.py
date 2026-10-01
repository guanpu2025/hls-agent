from __future__ import annotations

REPAIR_INSTRUCTION = """Continue your solution in <think>: identify the error's cause, what you will change, and why the change should fix it. Then submit the revised COMPLETE source file. Do not edit the header, testbench, or task description."""


def build_repair_user_message(
    *,
    csim_status: str,
    synth_status: str,
    failed_stage: str,
    tool_output: str,
    max_log_chars: int = 6000,
) -> str:
    log = tool_output.strip()
    if len(log) > max_log_chars:
        log = log[:max_log_chars] + "\n...[truncated]..."
    return (
        f"Vitis HLS 2025.2 result: CSim={csim_status}, Synthesis={synth_status}, "
        f"failed_stage={failed_stage}.\n"
        f"Relevant tool output:\n{log}\n\n"
        f"{REPAIR_INSTRUCTION}"
    )


def feedback_file_to_user_message(feedback_text: str) -> str:
    """Accept either a raw Vitis log or a full trajectory-style attempt_02 prompt."""
    text = feedback_text.strip()
    if "Continue your solution in <think>" in text or text.startswith("Vitis HLS"):
        return text
    return build_repair_user_message(
        csim_status="fail",
        synth_status="skipped_csim_failed",
        failed_stage="csim",
        tool_output=text,
    )
