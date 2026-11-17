"""Checks for world.py on the demo record.

Run: uv run python src/test/test_world.py  (also works under pytest)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "continuity_checker"))

import world  # noqa: E402


def _demo_db():
    return world.build(Path(tempfile.mkdtemp()) / "test.rl", demo=True)


def test_expected_and_states_at():
    db = _demo_db()
    assert world.expected(db, "カイ", "上着", 6)["value"] == "青"
    assert world.expected(db, "ミナ", "信頼", 2, toward="カイ")["value"] == "警戒"
    trust = world.expected(db, "ミナ", "信頼", 5, toward="カイ")
    assert trust["value"] == "信頼" and trust["since"] == 4
    assert world.expected(db, "ミナ", "信頼", 5) is None  # relationship states need toward
    rows = {(r["who"], r["attr"], r["toward"]): r["value"] for r in world.states_at(db, 6)}
    assert rows[("カイ", "上着", None)] == "青"
    assert rows[("ミナ", "信頼", "カイ")] == "信頼"
    assert rows[("グラス", "状態", None)] == "割れた"


def test_apply_change():
    db = _demo_db()
    world.apply_change(db, "カイ", "上着", "青", "なし", 5, "青い上着を脱ぐ")
    assert world.expected(db, "カイ", "上着", 4)["value"] == "青"
    after = world.expected(db, "カイ", "上着", 6)
    assert after == {"value": "なし", "cause": "青い上着を脱ぐ", "since": 5}
    rels = world.export(db)["rels"]
    states = {s["id"]: s for s in world.export(db)["states"]}
    new = [s for s in states.values() if s["value"] == "なし" and s["who"] == "カイ"][0]
    assert new["approved_by"] == "human" and new["to"] == world.END
    assert any(r["type"] == "STARTED_AT" and r["src"] == {"State": new["id"]} and r["dst"] == {"Shot": 5}
               for r in rels)
    assert any(r["type"] == "REPLACED_BY" and r["dst"] == {"State": new["id"]} for r in rels)
    try:
        world.apply_change(db, "カイ", "上着", "青", "なし", 6, "x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a missing State")


def test_relationship_change_and_fixed_relation():
    db = _demo_db()
    world.apply_change(db, "ミナ", "信頼", "信頼", "警戒", 6, "裏切る", toward="カイ")
    assert world.expected(db, "ミナ", "信頼", 6, toward="カイ")["value"] == "警戒"
    assert world.expected(db, "ミナ", "信頼", 5, toward="カイ")["value"] == "信頼"
    rels = world.export(db)["rels"]
    assert {"type": "RELATES_TO", "src": {"Entity": "カイ"}, "dst": {"Entity": "ミナ"},
            "props": {"kind": "部の先輩", "fixed": True}} in rels
    assert sum(r["type"] == "TOWARD" for r in rels) == 3


def test_full_record_unchanged():
    db = world.build(Path(tempfile.mkdtemp()) / "full.rl")
    assert world.expected(db, "カイ", "上着", 6)["value"] == "なし"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
