"""Backup LLM route: ai& inference (OpenAI-compatible), same `ask_json` interface as llm.py.

Setup guide: https://docs.aiand.com/ (Base URL https://api.aiand.com/v1, Bearer auth,
`response_format` json_schema for structured output). The key comes only from the
environment variable AIAND_API_KEY, filled by `scripts/run.sh` through
`api_secrets.run_with_key` (key id `aiand_api_key`). It is never printed.

    scripts/run.sh aiand            # self-test: one tiny call
    scripts/run.sh aiand-models     # list model ids the key can call
Model: AIAND_MODEL or `zai-org/glm-5.3-flash` (`auto` is not enabled for this organization).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("AIAND_BASE_URL", "https://api.aiand.com/v1")
MODEL = os.environ.get("AIAND_MODEL", "zai-org/glm-5.3-flash")
SYSTEM = "あなたは映像のつながり（コンティニュイティ）の記録係。指定されたJSONだけを返す。"


def _request(path: str, body: dict | None = None, timeout: int = 60):
    key = os.environ.get("AIAND_API_KEY")
    if not key:
        raise SystemExit("AIAND_API_KEY is not set: start this through scripts/run.sh")
    req = urllib.request.Request(
        BASE_URL + path,
        data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.headers.get("X-Model")
    except urllib.error.HTTPError as e:  # the body says why (credit, model, schema); it holds no key
        raise RuntimeError(f"ai& {e.code}: {e.read().decode(errors='replace')[:500]}") from None


def ask_json(prompt: str, schema: dict, model: str | None = None, timeout: int = 60) -> dict:
    body = {
        "model": model or MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer", "strict": True, "schema": {**schema, "additionalProperties": False}},
        },
    }
    data, _ = _request("/chat/completions", body, timeout)
    return json.loads(data["choices"][0]["message"]["content"])


def list_models() -> list[str]:
    data, _ = _request("/models")
    return sorted(m["id"] for m in data.get("data", []))


if __name__ == "__main__":
    if sys.argv[1:] == ["models"]:
        print("\n".join(list_models()))
    else:
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        print(ask_json("ok を true にして返して。", schema))
