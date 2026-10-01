"""Run Vitis HLS C-sim (via HLS-Eval tools) and optional golden stdout check."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Prefer lab HLS-Eval checkout
_HLS_EVAL_ROOT = Path(os.environ.get("HLS_EVAL_ROOT", "/data/guanpu/hls-eval"))
if _HLS_EVAL_ROOT.is_dir() and str(_HLS_EVAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_HLS_EVAL_ROOT))

from hls_eval.tools import (  # noqa: E402
    VitisHLSCSimTool,
    VitisHLSSynthTool,
    auto_find_vitis_hls_dir,
)


DEFAULT_PART = os.environ.get("HLS_FPGA_PART", "xczu3eg-sbva484-1-e")
DEFAULT_VITIS = Path(
    os.environ.get("XILINX_VITIS", "/data/guanpu/Xilinx/2025.2/Vitis")
)
DEFAULT_VIVADO = Path(
    os.environ.get("XILINX_VIVADO", "/data/guanpu/Xilinx/2025.2/Vivado")
)


def ensure_xilinx_env() -> None:
    """Make device libraries visible to vitis_hls (2025.2 needs XILINX_VIVADO)."""
    os.environ.setdefault("XILINX_VIVADO", str(DEFAULT_VIVADO))
    os.environ.setdefault("XILINX_VITIS", str(DEFAULT_VITIS))
    vitis_bin = str(DEFAULT_VITIS / "bin")
    vivado_bin = str(DEFAULT_VIVADO / "bin")
    path = os.environ.get("PATH", "")
    for p in (vitis_bin, vivado_bin):
        if p not in path.split(":"):
            path = p + ":" + path
    os.environ["PATH"] = path


@dataclass
class FeedbackResult:
    ok: bool
    csim_compile_ok: bool
    csim_run_ok: bool
    csim_return_code: int | None
    synth_ok: bool | None
    golden_match: bool | None
    failed_stage: str
    tool_output: str
    stdout: str

    def to_dict(self) -> dict:
        return asdict(self)


def _tail(text: str, n: int = 8000) -> str:
    text = text or ""
    return text if len(text) <= n else text[-n:]


def evaluate_sources(
    *,
    build_dir: Path,
    cpp_path: Path,
    header_path: Path,
    tb_path: Path,
    top_function: str,
    golden_stdout: str | None = None,
    run_synth: bool = False,
    fpga_part: str = DEFAULT_PART,
    timeout_csim: float = 300.0,
    timeout_synth: float = 600.0,
) -> FeedbackResult:
    ensure_xilinx_env()
    vitis_dir = auto_find_vitis_hls_dir()
    if vitis_dir is None:
        raise RuntimeError(
            "vitis_hls not on PATH; set PATH or XILINX_VITIS (expected "
            f"{DEFAULT_VITIS})"
        )

    build_dir.mkdir(parents=True, exist_ok=True)
    work = build_dir / "src"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    cpp_dst = work / cpp_path.name
    hdr_dst = work / header_path.name
    tb_dst = work / tb_path.name
    shutil.copy(cpp_path, cpp_dst)
    shutil.copy(header_path, hdr_dst)
    shutil.copy(tb_path, tb_dst)

    # HLS-Eval TCL embeds these paths; they must be absolute (vitis cwd ≠ caller cwd)
    cpp_dst = cpp_dst.resolve()
    hdr_dst = hdr_dst.resolve()
    tb_dst = tb_dst.resolve()

    csim = VitisHLSCSimTool(vitis_dir)
    compile_r, run_r = csim.run(
        build_dir,
        source_files=[cpp_dst, hdr_dst],
        aux_files=[tb_dst],
        build_name="agent",
        hls_top_function=top_function,
        hls_fpga_part=fpga_part,
        timeout=timeout_csim,
    )

    chunks: list[str] = []
    chunks.append("=== csim compile ===\n")
    chunks.append(_tail(compile_r.data_execution.stdout or ""))
    chunks.append(_tail(compile_r.data_execution.stderr or ""))

    compile_ok = (
        compile_r.data_execution.return_code == 0
        and not compile_r.data_execution.timeout
    )
    if not compile_ok:
        return FeedbackResult(
            ok=False,
            csim_compile_ok=False,
            csim_run_ok=False,
            csim_return_code=compile_r.data_execution.return_code,
            synth_ok=None,
            golden_match=None,
            failed_stage="csim_compile",
            tool_output="\n".join(chunks),
            stdout="",
        )

    run_ok = bool(
        run_r
        and run_r.data_execution.return_code == 0
        and not run_r.data_execution.timeout
    )
    stdout = (run_r.data_execution.stdout if run_r else "") or ""
    chunks.append("\n=== csim run ===\n")
    if run_r:
        chunks.append(_tail(run_r.data_execution.stdout or ""))
        chunks.append(_tail(run_r.data_execution.stderr or ""))
    else:
        chunks.append("(no run result)\n")

    if not run_ok:
        return FeedbackResult(
            ok=False,
            csim_compile_ok=True,
            csim_run_ok=False,
            csim_return_code=run_r.data_execution.return_code if run_r else None,
            synth_ok=None,
            golden_match=None,
            failed_stage="csim_run",
            tool_output="\n".join(chunks),
            stdout=stdout,
        )

    golden_match: bool | None = None
    if golden_stdout is not None:
        golden_match = stdout.strip() == golden_stdout.strip()
        chunks.append("\n=== golden stdout check ===\n")
        chunks.append(f"expected: {golden_stdout.strip()!r}\n")
        chunks.append(f"actual:   {stdout.strip()!r}\n")
        chunks.append(f"match: {golden_match}\n")
        if not golden_match:
            return FeedbackResult(
                ok=False,
                csim_compile_ok=True,
                csim_run_ok=True,
                csim_return_code=0,
                synth_ok=None,
                golden_match=False,
                failed_stage="golden_mismatch",
                tool_output="\n".join(chunks),
                stdout=stdout,
            )

    synth_ok: bool | None = None
    if run_synth:
        synth = VitisHLSSynthTool(vitis_dir)
        synth_r = synth.run(
            build_dir,
            source_files=[cpp_dst, hdr_dst],
            build_name="agent_synth",
            hls_top_function=top_function,
            hls_fpga_part=fpga_part,
            timeout=timeout_synth,
        )
        chunks.append("\n=== synth ===\n")
        chunks.append(_tail(synth_r.data_execution.stdout or ""))
        chunks.append(_tail(synth_r.data_execution.stderr or ""))
        synth_ok = (
            synth_r.data_execution.return_code == 0
            and not synth_r.data_execution.timeout
        )
        if not synth_ok:
            return FeedbackResult(
                ok=False,
                csim_compile_ok=True,
                csim_run_ok=True,
                csim_return_code=0,
                synth_ok=False,
                golden_match=golden_match,
                failed_stage="synth",
                tool_output="\n".join(chunks),
                stdout=stdout,
            )

    return FeedbackResult(
        ok=True,
        csim_compile_ok=True,
        csim_run_ok=True,
        csim_return_code=0,
        synth_ok=synth_ok,
        golden_match=golden_match if golden_stdout is not None else None,
        failed_stage="none",
        tool_output="\n".join(chunks),
        stdout=stdout,
    )
