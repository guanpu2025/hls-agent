from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE = os.environ.get("HLS_API_BASE", "http://192.168.0.157:8731/v1")
DEFAULT_MODEL = os.environ.get("HLS_MODEL", "halogen-qwen3.8-flash-next")


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = float(os.environ.get("HLS_API_TIMEOUT", "1800")),
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"LLM request failed ({self.base_url}): {e}. "
                "On laptop use SSH tunnel: ./start_tunnel.sh and "
                "HLS_API_BASE=http://127.0.0.1:18731/v1"
            ) from e

        try:
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning_content") or "").strip()
            text = content or reasoning
            if not text:
                raise RuntimeError(f"Empty message content: {data!r}")
            return text
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected LLM response: {data!r}") from e
