"""Tests for checker (toward, 16 cases) and propose (guards, cache, fallback).

world.py is being rewritten in parallel (W1), so expected / states_at / registry are
replaced here by a tiny local stub over the demo record from the interface contract.
Run: uv run python -m unittest discover -s src/test -v
Live claude -p call (about USD 0.01): CC_LIVE=1 uv run python -m unittest discover -s src/test -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "continuity_checker"))

import checker  # noqa: E402
import propose  # noqa: E402
import world  # noqa: E402

END = 99

# Demo record: STATES without the S5 jacket change (カイ 上着 青 to END), plus the
# relationship state ミナ→カイ 信頼. Rows: (who, attr, value, from, to, cause, toward)
DEMO = [
    (e, a, v, f, END if (e, a, v) == ("カイ", "上着", "青") else t, c, None)
    for e, a, v, f, t, c in world.STATES
    if (e, a, v) != ("カイ", "上着", "なし")
] + [
    ("ミナ", "信頼", "警戒", 1, 3, "S1 設定", "カイ"),
    ("ミナ", "信頼", "信頼", 4, END, "S4 カイがミナに鍵を渡す", "カイ"),
]


def stub_expected(db, entity, attr, shot, toward=None):
    for who, a, v, f, t, c, tw in db:
        if who == entity and a == attr and tw == toward and f <= shot <= t:
            return {"value": v, "cause": c, "since": f}
    return None


def stub_states_at(db, shot):
    return [{"who": w, "attr": a, "toward": tw, "value": v, "cause": c}
            for w, a, v, f, t, c, tw in db if f <= shot <= t]


def stub_registry():
    attrs, rels = {}, {}
    rows = [(w, a, v, tw) for w, a, v, *_r, tw in DEMO]
    rows += [(r[1], r[2], r[3], r[4] if len(r) > 4 else None) for r in checker.LEXICON]
    rows.append(("カイ", "上着", "なし", None))
    for who, a, v, tw in rows:
        target = rels.setdefault((who, tw), {}) if tw else attrs.setdefault(who, {})
        vals = target.setdefault(a, [])
        if v not in vals:
            vals.append(v)
    return {"entities": [n for _k, n in world.ENTITIES], "attrs": attrs, "relations": rels}


class StubWorld(unittest.TestCase):
    def setUp(self):
        self.db = list(DEMO)
        self.patches = [
            mock.patch.object(world, "expected", stub_expected, create=True),
            mock.patch.object(world, "states_at", stub_states_at, create=True),
            mock.patch.object(world, "registry", stub_registry, create=True),
        ]
        for p in self.patches:
            p.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.patches.append(mock.patch.object(propose, "CACHE_PATH", Path(self.tmp.name) / "c.json"))
        self.patches[-1].start()
        propose._cache = None

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()
        propose._cache = None


class CheckerTests(StubWorld):
    def test_claim_toward_default(self):
        self.assertIsNone(checker.Claim("カイ", "上着", "青", 0, 4).toward)

    def test_relationship_claim(self):
        (c,) = checker.extract("ミナがカイを警戒して距離をとる。")
        self.assertEqual((c.entity, c.attr, c.value, c.toward), ("ミナ", "信頼", "警戒", "カイ"))
        (f,) = checker.check_with_graph(self.db, 7, "ミナがカイを警戒して距離をとる。")
        self.assertEqual(f.status, "矛盾")

    def test_eval_16_before_approval(self):
        rows, score, n_bad, n_ok = checker.evaluate(self.db)
        self.assertEqual((len(rows), n_bad, n_ok), (16, 10, 6))
        self.assertEqual(score["graph"], [10, 1])  # the one false positive: S6 上着なし
        self.assertEqual(score["base"], [3, 1])

    def test_eval_after_approval(self):
        db = [r for r in self.db if r[:3] != ("カイ", "上着", "青")]
        db += [("カイ", "上着", "青", 1, 4, "S1 設定", None),
               ("カイ", "上着", "なし", 5, END, "青い上着を脱ぐ", None)]
        _rows, score, _b, _o = checker.evaluate(db)
        self.assertEqual(score["graph"], [10, 0])


class GuardTests(StubWorld):
    def test_rejects_sword_without_change_verb(self):
        text = "ミナが剣を右手で振る。"
        ok, reason = propose.guard(self.db, 7, text, {
            "entity": "剣", "attr": "持ち手", "from": "左手", "to": "右手",
            "cause_quote": "剣を右手で振る"})
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("ガード③"), reason)

    def test_accepts_jacket_off(self):
        ok, reason = propose.guard(self.db, 5, "カイが青い上着を脱ぐ。", {
            "entity": "カイ", "attr": "上着", "from": "青", "to": "なし",
            "cause_quote": "青い上着を脱ぐ"})
        self.assertTrue(ok, reason)

    def test_other_rules(self):
        text = "カイが青い上着を脱ぐ。"
        base = {"entity": "カイ", "attr": "上着", "from": "青", "to": "なし", "cause_quote": "青い上着を脱ぐ"}
        cases = [({"to": "緑"}, "ガード①"), ({"entity": "サキ"}, "ガード①"),
                 ({"cause_quote": "上着を脱いだ"}, "ガード②"), ({"from": "なし", "to": "青"}, "ガード④")]
        for patch, rule in cases:
            ok, reason = propose.guard(self.db, 5, text, {**base, **patch})
            self.assertFalse(ok, patch)
            self.assertTrue(reason.startswith(rule), (patch, reason))

    def test_relationship_guard(self):
        text = "カイがミナを裏切る。"
        ch = {"entity": "ミナ", "attr": "信頼", "from": "信頼", "to": "警戒",
              "cause_quote": "カイがミナを裏切る", "toward": "カイ"}
        self.assertEqual(propose.guard(self.db, 7, text, ch), (True, "ガード通過"))
        self.assertFalse(propose.guard(self.db, 7, text, {**ch, "toward": "サキ"})[0])

    def test_conjugated_verb(self):
        self.assertTrue(propose.has_change_verb("上着を脱いで"))
        self.assertFalse(propose.has_change_verb("剣を右手で振る"))


class ProposeTests(StubWorld):
    ANSWER = {"kind": "change", "changes": [
        {"entity": "カイ", "attr": "上着", "from": "青", "to": "なし", "cause_quote": "青い上着を脱ぐ"}]}

    def test_cache_and_guard(self):
        with mock.patch.object(propose.llm, "ask_json", return_value=self.ANSWER) as ask:
            (p,) = propose.propose_change(self.db, 5, "カイが青い上着を脱ぐ。")
            propose._cache = None  # force a reload from the file
            propose.propose_change(self.db, 5, "カイが青い上着を脱ぐ。")
        self.assertEqual(ask.call_count, 1)
        self.assertTrue(p.ok)
        self.assertEqual((p.frm, p.to, p.toward), ("青", "なし", None))
        self.assertTrue(propose.CACHE_PATH.exists())

    def test_llm_failure_returns_empty(self):
        with mock.patch.object(propose.llm, "ask_json", side_effect=RuntimeError("boom")):
            self.assertEqual(propose.propose_change(self.db, 5, "x"), [])
        self.assertTrue(propose.last_error.startswith(propose.FAILED))
        self.assertFalse(propose.CACHE_PATH.exists())  # failures are not cached


@unittest.skipUnless(os.environ.get("CC_LIVE") == "1", "set CC_LIVE=1 for the live claude -p call")
class LiveTests(StubWorld):
    def test_live_s5(self):
        props = propose.propose_change(self.db, 5, "カイが青い上着を脱ぐ。")
        print("\nlive:", props, propose.last_error)
        self.assertIsNone(propose.last_error)
        self.assertTrue(any(p.ok and (p.entity, p.attr, p.frm, p.to) == ("カイ", "上着", "青", "なし")
                            for p in props), props)


if __name__ == "__main__":
    unittest.main()
