"""Single-shot baseline: one prompt → one generation (no repair, no tools)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.extract import parse_answer  # noqa: E402
from agent.llm_client import LLMClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="HLS baseline: single LLM generation")
    ap.add_argument("--prompt", type=Path, required=True, help="Full user prompt file")
    ap.add_argument("--out", type=Path, required=True, help="Output directory")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--system", type=str, default="", help="Optional system message")
    args = ap.parse_args()

    prompt = args.prompt.read_text(encoding="utf-8")
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    messages: list[dict[str, str]] = []
    if args.system.strip():
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    client = LLMClient()
    raw = client.chat(messages, max_tokens=args.max_tokens)
    parsed = parse_answer(raw)

    (out / "raw_output.txt").write_text(raw, encoding="utf-8")
    if parsed.think:
        (out / "think.txt").write_text(parsed.think, encoding="utf-8")
    code_name = parsed.code_name or "generated.cpp"
    if parsed.code:
        (out / code_name).write_text(parsed.code + "\n", encoding="utf-8")
        (out / "generated.cpp").write_text(parsed.code + "\n", encoding="utf-8")

    meta = {
        "mode": "baseline",
        "model": client.model,
        "base_url": client.base_url,
        "parse_ok": parsed.ok,
        "code_name": parsed.code_name,
        "prompt": str(args.prompt),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not parsed.ok:
        print("WARN: failed to extract <OUTPUT_CODE>", file=sys.stderr)
        return 2
    print(f"wrote {out / 'generated.cpp'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
