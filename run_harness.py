"""Initial harness: generate → Vitis/HLS-Eval feedback → at most one repair.

Max model calls = 2. Designed for short prompts on memory-tight halogen hosts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.extract import parse_answer  # noqa: E402
from agent.llm_client import LLMClient  # noqa: E402
from agent.prompts import build_repair_user_message  # noqa: E402
from agent.vitis_runner import evaluate_sources  # noqa: E402


def _save_round(out: Path, tag: str, raw: str) -> dict:
    parsed = parse_answer(raw)
    round_dir = out / tag
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "raw_output.txt").write_text(raw, encoding="utf-8")
    if parsed.think:
        (round_dir / "think.txt").write_text(parsed.think, encoding="utf-8")
    code_name = parsed.code_name or "generated.cpp"
    if parsed.code:
        (round_dir / code_name).write_text(parsed.code + "\n", encoding="utf-8")
        (round_dir / "generated.cpp").write_text(parsed.code + "\n", encoding="utf-8")
        (out / "generated.cpp").write_text(parsed.code + "\n", encoding="utf-8")
    return {
        "tag": tag,
        "parse_ok": parsed.ok,
        "code_name": parsed.code_name,
        "code_chars": len(parsed.code or ""),
    }


def _stage_cpp(out: Path, design_dir: Path, cpp_name: str) -> Path:
    """Write latest generated.cpp into a work copy named like the design kernel."""
    src = out / "generated.cpp"
    if not src.exists():
        raise FileNotFoundError(f"missing {src}")
    work = out / "design_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    hdr_candidates = list(design_dir.glob("*.h"))
    tb_candidates = list(design_dir.glob("*_tb.cpp"))
    if not hdr_candidates or not tb_candidates:
        raise FileNotFoundError(f"design_dir {design_dir} needs *.h and *_tb.cpp")
    header = hdr_candidates[0]
    tb = tb_candidates[0]
    shutil.copy(src, work / cpp_name)
    shutil.copy(header, work / header.name)
    shutil.copy(tb, work / tb.name)
    return work


def _evaluate(
    out: Path,
    design_dir: Path,
    cpp_name: str,
    top: str,
    golden: str | None,
    run_synth: bool,
    tag: str,
) -> dict:
    work = _stage_cpp(out, design_dir, cpp_name)
    cpp_path = work / cpp_name
    header = next(work.glob("*.h"))
    tb = next(work.glob("*_tb.cpp"))
    build = out / f"vitis_{tag}"
    result = evaluate_sources(
        build_dir=build,
        cpp_path=cpp_path,
        header_path=header,
        tb_path=tb,
        top_function=top,
        golden_stdout=golden,
        run_synth=run_synth,
    )
    fb_path = out / f"feedback_{tag}.txt"
    fb_path.write_text(result.tool_output, encoding="utf-8")
    meta = result.to_dict()
    meta["feedback_file"] = str(fb_path)
    (out / f"feedback_{tag}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description="HLS initial harness (gen + feedback + repair)")
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--design-dir",
        type=Path,
        required=True,
        help="HLS-Eval-style design dir with header + *_tb.cpp (+ optional golden.txt)",
    )
    ap.add_argument("--top", type=str, default=None, help="Top function (default: top.txt)")
    ap.add_argument("--cpp-name", type=str, default=None, help="Kernel .cpp filename")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--synth", action="store_true", help="Also run csynth after csim")
    ap.add_argument("--skip-llm", action="store_true", help="Evaluate existing generated.cpp only")
    ap.add_argument(
        "--seed-cpp",
        type=Path,
        default=None,
        help="Use this cpp as attempt_01 instead of calling the LLM",
    )
    args = ap.parse_args()

    design_dir: Path = args.design_dir
    if not design_dir.is_dir():
        print(f"design-dir not found: {design_dir}", file=sys.stderr)
        return 1

    top = args.top
    if not top:
        top_file = design_dir / "top.txt"
        top = top_file.read_text(encoding="utf-8").strip() if top_file.exists() else None
    if not top:
        print("need --top or design-dir/top.txt", file=sys.stderr)
        return 1

    cpp_name = args.cpp_name
    if not cpp_name:
        cps = [
            p.name
            for p in design_dir.glob("*.cpp")
            if not p.name.endswith("_tb.cpp") and not p.name.startswith("broken_")
        ]
        if not cps:
            print("no kernel .cpp in design-dir; pass --cpp-name", file=sys.stderr)
            return 1
        # Prefer <stem>.cpp matching top.txt lowercased if present
        prefer = f"{top}.cpp" if top else None
        if prefer and prefer in cps:
            cpp_name = prefer
        elif f"{top[0].lower() + top[1:]}.cpp" in cps:
            # ShiftRows -> shift_rows.cpp heuristic
            import re

            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", top).lower() + ".cpp"
            cpp_name = snake if snake in cps else sorted(cps)[0]
        else:
            snake = None
            try:
                import re

                snake = re.sub(r"(?<!^)(?=[A-Z])", "_", top).lower() + ".cpp"
            except Exception:
                snake = None
            cpp_name = snake if snake and snake in cps else sorted(cps)[0]

    golden = None
    golden_file = design_dir / "golden_stdout.txt"
    if golden_file.exists():
        golden = golden_file.read_text(encoding="utf-8")

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt_used.txt").write_text(args.prompt.read_text(encoding="utf-8"), encoding="utf-8")

    client = LLMClient()
    rounds_meta: list[dict] = []
    messages: list[dict[str, str]] = [
        {"role": "user", "content": args.prompt.read_text(encoding="utf-8")}
    ]

    # ---- Round 1: generate or seed ----
    if args.seed_cpp is not None:
        code = args.seed_cpp.read_text(encoding="utf-8")
        raw1 = f'<OUTPUT_CODE name="{cpp_name}">\n{code.rstrip()}\n</OUTPUT_CODE>'
        rounds_meta.append(_save_round(out, "attempt_01", raw1))
    elif args.skip_llm:
        if not (out / "generated.cpp").exists():
            print("--skip-llm requires existing out/generated.cpp", file=sys.stderr)
            return 1
        rounds_meta.append(
            {
                "tag": "attempt_01",
                "parse_ok": True,
                "code_name": cpp_name,
                "code_chars": (out / "generated.cpp").stat().st_size,
                "skipped_llm": True,
            }
        )
    else:
        raw1 = client.chat(messages, max_tokens=args.max_tokens)
        rounds_meta.append(_save_round(out, "attempt_01", raw1))
        messages.append({"role": "assistant", "content": raw1})
        if not rounds_meta[-1]["parse_ok"]:
            meta = {
                "mode": "harness_v1",
                "error": "parse_failed_round1",
                "rounds": rounds_meta,
            }
            (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(json.dumps(meta, indent=2))
            return 2

    fb1 = _evaluate(out, design_dir, cpp_name, top, golden, args.synth, "01")
    evals = [fb1]

    # ---- Round 2: repair if needed ----
    if (not fb1["ok"]) and args.max_rounds >= 2 and not args.skip_llm and args.seed_cpp is None:
        repair_user = build_repair_user_message(
            csim_status="pass" if fb1["csim_run_ok"] else "fail",
            synth_status=(
                "pass"
                if fb1.get("synth_ok")
                else ("fail" if fb1.get("synth_ok") is False else "skipped")
            ),
            failed_stage=fb1["failed_stage"],
            tool_output=Path(fb1["feedback_file"]).read_text(encoding="utf-8"),
        )
        # Keep repair prompt short for halogen memory limits
        if len(repair_user) > 4500:
            repair_user = repair_user[:4500] + "\n...[truncated for halogen]...\n"
            repair_user += (
                "Resubmit the COMPLETE fixed source in "
                f'<OUTPUT_CODE name="{cpp_name}">...</OUTPUT_CODE> only.\n'
            )
        (out / "repair_user.txt").write_text(repair_user, encoding="utf-8")
        messages.append({"role": "user", "content": repair_user})
        raw2 = client.chat(messages, max_tokens=args.max_tokens)
        rounds_meta.append(_save_round(out, "attempt_02", raw2))
        if rounds_meta[-1]["parse_ok"]:
            fb2 = _evaluate(out, design_dir, cpp_name, top, golden, args.synth, "02")
            evals.append(fb2)

    final_ok = bool(evals and evals[-1]["ok"])
    meta = {
        "mode": "harness_v1",
        "model": client.model,
        "base_url": client.base_url,
        "design_dir": str(design_dir),
        "top": top,
        "cpp_name": cpp_name,
        "max_rounds": args.max_rounds,
        "rounds": rounds_meta,
        "evaluations": evals,
        "final_ok": final_ok,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"final_ok={final_ok} out={out}")
    return 0 if final_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
