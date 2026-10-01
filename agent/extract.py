from __future__ import annotations

import re
from dataclasses import dataclass


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_CODE_RE = re.compile(
    r'<OUTPUT_CODE\s+name="([^"]+)">(.*?)</OUTPUT_CODE>',
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class ParsedAnswer:
    think: str | None
    code_name: str | None
    code: str | None
    raw: str

    @property
    def ok(self) -> bool:
        return bool(self.code and self.code.strip())


_FENCE_RE = re.compile(r"```(?:cpp|c\+\+|c)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_answer(text: str) -> ParsedAnswer:
    think_m = _THINK_RE.search(text)
    code_m = _CODE_RE.search(text)
    code_name = code_m.group(1).strip() if code_m else None
    code = code_m.group(2).strip() if code_m else None
    # Smoke / plain replies: accept fenced or raw C++ when OUTPUT_CODE missing
    if not code:
        fence_m = _FENCE_RE.search(text)
        if fence_m:
            code = fence_m.group(1).strip()
            code_name = code_name or "generated.cpp"
        else:
            stripped = text.strip()
            if "int " in stripped or "void " in stripped or "#include" in stripped:
                code = stripped
                code_name = code_name or "generated.cpp"
    return ParsedAnswer(
        think=think_m.group(1).strip() if think_m else None,
        code_name=code_name,
        code=code,
        raw=text,
    )
