"""Two-step harness: generate once, optional one repair from Vitis feedback.

max model calls = 2 (aligned with Luna trajectories / competition gain story).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.extract import parse_answer  # noqa: E402
from agent.llm_client import LLMClient  # noqa: E402
from agent.prompts import feedback_file_to_user_message  # noqa: E402


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


def main() -> int:
    ap = argparse.ArgumentParser(description="HLS agent: generate + at most one repair")
    ap.add_argument("--prompt", type=Path, required=True, help="Initial full prompt")
    ap.add_argument(
        "--feedback",
        type=Path,
        default=None,
        help="Vitis log or trajectory-style repair user message (triggers 2nd call)",
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--system", type=str, default="")
    ap.add_argument(
        "--max-rounds",
        type=int,
        default=2,
        help="Hard cap on model calls (default 2)",
    )
    args = ap.parse_args()

    if args.max_rounds < 1:
        print("--max-rounds must be >= 1", file=sys.stderr)
        return 1

    prompt = args.prompt.read_text(encoding="utf-8")
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    messages: list[dict[str, str]] = []
    if args.system.strip():
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    client = LLMClient()
    rounds_meta: list[dict] = []

    # Round 1 — generate
    raw1 = client.chat(messages, max_tokens=args.max_tokens)
    rounds_meta.append(_save_round(out, "attempt_01", raw1))
    messages.append({"role": "assistant", "content": raw1})

    # Round 2 — repair (only if feedback provided and under cap)
    if args.feedback is not None and args.max_rounds >= 2:
        fb = args.feedback.read_text(encoding="utf-8")
        repair_user = feedback_file_to_user_message(fb)
        (out / "repair_user.txt").write_text(repair_user, encoding="utf-8")
        messages.append({"role": "user", "content": repair_user})
        raw2 = client.chat(messages, max_tokens=args.max_tokens)
        rounds_meta.append(_save_round(out, "attempt_02", raw2))

    meta = {
        "mode": "agent_two_step",
        "model": client.model,
        "base_url": client.base_url,
        "max_rounds": args.max_rounds,
        "feedback": str(args.feedback) if args.feedback else None,
        "rounds": rounds_meta,
        "final_parse_ok": bool(rounds_meta and rounds_meta[-1]["parse_ok"]),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not meta["final_parse_ok"]:
        return 2
    print(f"wrote {out / 'generated.cpp'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
