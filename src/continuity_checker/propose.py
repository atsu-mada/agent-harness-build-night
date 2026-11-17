"""Propose state changes for a shot with the LLM, then check them with four guards.

The LLM only says what changed and quotes the cause from the shot text. Code decides
whether the proposal may be shown as approvable:
  1. entity, attr, from/to (and the TOWARD character) are registered;
  2. cause_quote appears verbatim in the shot text;
  3. cause_quote contains a registered change verb;
  4. from equals the recorded value at shot-1.
Nothing is written here: a human approves, and world.apply_change() writes.

Raw LLM answers are cached by (shot, text) in memory and in data/logs/propose_cache.json,
so reruns are instant; guards always run again against the current record.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import llm
import world

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "logs" / "propose_cache.json"

CHANGE_VERBS = [
    "脱ぐ", "着る", "外す", "かける", "渡す", "受け取る", "持ち替える", "落とす",
    "割れる", "割る", "閉める", "開ける", "飲む", "つまずく", "ケガ", "なくす", "出ていく",
    # relationship changes
    "助ける", "打ち明ける", "裏切る", "許す", "守る",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["change", "none"]},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "attr": {"type": "string"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "cause_quote": {"type": "string"},
                    "toward": {"type": "string"},
                },
                "required": ["entity", "attr", "from", "to", "cause_quote"],
            },
        },
    },
    "required": ["kind", "changes"],
}

FAILED = "提案を作れなかった"


@dataclass
class Proposal:
    entity: str
    attr: str
    frm: str
    to: str
    cause_quote: str
    toward: str | None
    ok: bool
    reason: str


# Reason for the last empty result: None (LLM said no change) or FAILED (+ detail).
last_error: str | None = None

_cache: dict[str, dict] | None = None


def _key(shot: int, text: str) -> str:
    return f"{shot}\t{text}"


def _load_cache() -> dict[str, dict]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # the cache is a convenience; never fail the app over it


def _verb_pattern(verb: str) -> str:
    """Dictionary form, or the stem followed by kana (脱いで, 渡した, 外し...)."""
    if not re.search(r"[ぁ-ん]$", verb):
        return re.escape(verb)  # noun such as ケガ
    return re.escape(verb[:-1]) + r"[ぁ-ん]"


_VERB_RE = re.compile("|".join(_verb_pattern(v) for v in CHANGE_VERBS))


def has_change_verb(quote: str) -> bool:
    return bool(_VERB_RE.search(quote))


def guard(db, shot: int, text: str, change: dict) -> tuple[bool, str]:
    """Apply the four guards to one proposed change; returns (ok, reason in Japanese)."""
    ent = change.get("entity", "")
    attr = change.get("attr", "")
    frm = change.get("from", "")
    to = change.get("to", "")
    quote = change.get("cause_quote", "") or ""
    toward = change.get("toward") or None

    # 1. registered names and values
    reg = world.registry()
    if ent not in reg.get("entities", []):
        return False, f"ガード①：未登録の対象「{ent}」"
    if toward is not None:
        if toward not in reg.get("entities", []):
            return False, f"ガード①：未登録の相手「{toward}」"
        allowed = reg.get("relations", {}).get((ent, toward), {}).get(attr)
        label = f"{ent}→{toward}の{attr}"
    else:
        allowed = reg.get("attrs", {}).get(ent, {}).get(attr)
        label = f"{ent}の{attr}"
    if allowed is None:
        return False, f"ガード①：未登録の属性「{label}」"
    for v in (frm, to):
        if v not in allowed:
            return False, f"ガード①：未登録の値「{v}」（{label}）"
    if frm == to:
        return False, f"ガード①：変化していない（{frm}→{to}）"

    # 2. the cause is quoted verbatim from the shot text
    if not quote or quote not in text:
        return False, f"ガード②：原因の引用「{quote}」が本文にない"

    # 3. the cause contains a change verb
    if not has_change_verb(quote):
        return False, f"ガード③：原因に変化の動詞がない（「{quote}」）"

    # 4. from matches the record just before this shot
    rec = world.expected(db, ent, attr, shot - 1, toward=toward)
    if rec is None:
        return False, f"ガード④：S{shot - 1}の記録がない（{label}）"
    if rec["value"] != frm:
        return False, f"ガード④：S{shot - 1}の記録は「{rec['value']}」で「{frm}」ではない"
    return True, "ガード通過"


def _prompt(db, shot: int, text: str) -> str:
    reg = world.registry()
    attrs = {e: {a: list(v) for a, v in av.items()} for e, av in reg.get("attrs", {}).items()}
    rels = {f"{a}→{b}": {k: list(v) for k, v in av.items()}
            for (a, b), av in reg.get("relations", {}).items()}
    record = [
        {k: r.get(k) for k in ("who", "attr", "toward", "value", "cause") if r.get(k) is not None}
        for r in world.states_at(db, shot - 1)
    ] if shot > 1 else []
    return (
        "ショットの文章を読み、このショットで起きた状態の変化だけを答える。\n"
        "- 変化がなければ kind を none、changes を空にする。\n"
        "- 状態が書かれているだけで、変化させる出来事がなければ変化ではない。\n"
        "- entity・attr・from・to は下の登録済みの名前と値だけを使う。from は直前の記録の値。\n"
        "- 人物どうしの関係の変化は toward に相手の名前を入れる（関係の属性を使う）。\n"
        "- cause_quote は原因となる出来事を本文からそのまま抜き出す（言い換えない）。\n\n"
        f"ショット: S{shot}\n本文: {text}\n\n"
        f"登録済みの対象: {json.dumps(reg.get('entities', []), ensure_ascii=False)}\n"
        f"属性と値: {json.dumps(attrs, ensure_ascii=False)}\n"
        f"関係の属性と値: {json.dumps(rels, ensure_ascii=False)}\n"
        f"S{shot - 1}時点の記録: {json.dumps(record, ensure_ascii=False)}\n"
    )


def _ask(db, shot: int, text: str) -> dict:
    cache = _load_cache()
    key = _key(shot, text)
    if key not in cache:
        cache[key] = llm.ask_json(_prompt(db, shot, text), SCHEMA)
        _save_cache()
    return cache[key]


def propose_change(db, shot: int, text: str) -> list[Proposal]:
    """LLM proposals for this shot, each checked by the guards. Never raises."""
    global last_error
    last_error = None
    try:
        answer = _ask(db, shot, text)
    except Exception as exc:  # claude -p missing, timeout, bad JSON, ...
        last_error = f"{FAILED}（{type(exc).__name__}）"
        return []
    if answer.get("kind") != "change":
        return []
    out = []
    for ch in answer.get("changes", []) or []:
        if not isinstance(ch, dict):
            continue
        try:
            ok, reason = guard(db, shot, text, ch)
        except Exception as exc:  # a guard must not crash the app either
            ok, reason = False, f"ガードの確認に失敗（{type(exc).__name__}）"
        out.append(Proposal(
            entity=ch.get("entity", ""), attr=ch.get("attr", ""),
            frm=ch.get("from", ""), to=ch.get("to", ""),
            cause_quote=ch.get("cause_quote", ""), toward=ch.get("toward") or None,
            ok=ok, reason=reason,
        ))
    return out


if __name__ == "__main__":
    import sys
    db = world.reset()
    shot = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    text = sys.argv[2] if len(sys.argv) > 2 else "カイが青い上着を脱ぐ。"
    for p in propose_change(db, shot, text):
        print(p)
    if last_error:
        print(last_error)
