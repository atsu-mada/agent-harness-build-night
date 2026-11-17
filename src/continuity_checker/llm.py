"""Call Claude through the local Claude Code CLI (`claude -p`) and get structured JSON back.

The flags keep each call small: no user settings, CLAUDE.md, skills, MCP servers or tools are
loaded, so a call costs about 1.7k input tokens instead of the whole client context.
Measured on 2026-11-17: about 3 s and USD 0.0075 per call with Sonnet.
"""
from __future__ import annotations

import json
import subprocess

SYSTEM = "あなたは映像のつながり（コンティニュイティ）の記録係。指定されたJSONだけを返す。"


def ask_json(prompt: str, schema: dict, model: str = "sonnet", timeout: int = 60) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--json-schema", json.dumps(schema, ensure_ascii=False),
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--system-prompt", SYSTEM,
        "--model", model,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    data = json.loads(out.stdout)
    if data.get("is_error"):
        raise RuntimeError(data.get("result") or "claude -p returned an error")
    return data["structured_output"]


if __name__ == "__main__":
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    print(ask_json("ok を true にして返して。", schema))
