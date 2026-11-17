"""Continuity checker: claim extraction, graph check, no-memory baseline, eval.

Extraction is a phrase lexicon for now (deterministic, works offline).
At the venue it can be swapped for an LLM extractor that returns the same
(entity, attr, value, start, end) tuples; the check itself stays a graph
query, so red marks never come from model prose.
"""
from __future__ import annotations

from dataclasses import dataclass

import world

# (phrase in the shot text, entity, attr, value[, toward])
# A 5th item names the other character of a relationship state (TOWARD).
LEXICON = [
    ("剣を右手", "剣", "持ち手", "右手"),
    ("右手の剣", "剣", "持ち手", "右手"),
    ("剣を左手", "剣", "持ち手", "左手"),
    ("左手の剣", "剣", "持ち手", "左手"),
    ("カイが鍵", "鍵", "持ち主", "カイ"),
    ("ミナが鍵", "鍵", "持ち主", "ミナ"),
    ("ミナに鍵を渡す", "鍵", "持ち主", "ミナ"),
    ("カイが走", "カイ", "左足", "無事"),
    ("足を引きずるカイ", "カイ", "左足", "ケガ"),
    ("開いたドア", "部室", "ドア", "開"),
    ("ドアが開", "部室", "ドア", "開"),
    ("ドアを閉める", "部室", "ドア", "閉"),
    ("昼の光", "部室", "時間帯", "昼"),
    ("夜・", "部室", "時間帯", "夜"),
    ("月明かり", "部室", "時間帯", "夜"),
    ("雨上がり", "部室", "天気", "雨上がり"),
    ("雨が降", "部室", "天気", "雨"),
    ("画面左に立つ", "ミナ", "立ち位置", "画面左"),
    ("ミナが画面左", "ミナ", "立ち位置", "画面左"),
    ("ミナが画面右", "ミナ", "立ち位置", "画面右"),
    ("カイは画面右", "カイ", "立ち位置", "画面右"),
    ("カイが画面右", "カイ", "立ち位置", "画面右"),
    ("カイが画面左", "カイ", "立ち位置", "画面左"),
    ("机の左にノートPC", "ノートPC", "位置", "机の左"),
    ("机の右にノートPC", "ノートPC", "位置", "机の右"),
    ("赤い上着", "ミナ", "上着", "赤"),
    ("青い上着", "カイ", "上着", "青"),
    ("上着なしのカイ", "カイ", "上着", "なし"),
    ("満杯のコーヒー", "コーヒー", "量", "満杯"),
    ("コーヒーを半分", "コーヒー", "量", "半分"),
    ("半分残ったコーヒー", "コーヒー", "量", "半分"),
    ("割れたグラス", "グラス", "状態", "割れた"),
    ("グラスが割れる", "グラス", "状態", "割れた"),
    ("無傷のグラス", "グラス", "状態", "無事"),
    ("眼鏡のカイ", "カイ", "眼鏡", "あり"),
    ("眼鏡を外したカイ", "カイ", "眼鏡", "なし"),
    ("ポニーテール", "ミナ", "髪型", "ポニーテール"),
    ("髪を下ろしたミナ", "ミナ", "髪型", "下ろし髪"),
    ("ミナが左手で書く", "ミナ", "利き手", "左"),
    # relationship states (who, attr, value, toward)
    ("カイを警戒", "ミナ", "信頼", "警戒", "カイ"),
    ("カイを信じる", "ミナ", "信頼", "信頼", "カイ"),
]


@dataclass
class Claim:
    entity: str
    attr: str
    value: str
    start: int
    end: int
    toward: str | None = None


@dataclass
class Finding:
    claim: Claim
    status: str  # "矛盾" / "OK" / "不明"
    note: str


def extract(text: str) -> list[Claim]:
    claims, taken = [], set()
    for row in sorted(LEXICON, key=lambda r: -len(r[0])):
        phrase, ent, attr, value = row[:4]
        toward = row[4] if len(row) > 4 else None
        start = text.find(phrase)
        while start != -1:
            span = set(range(start, start + len(phrase)))
            if not span & taken:
                taken |= span
                claims.append(Claim(ent, attr, value, start, start + len(phrase), toward))
            start = text.find(phrase, start + 1)
    return sorted(claims, key=lambda c: c.start)


def check_with_graph(db, shot: int, text: str) -> list[Finding]:
    """Harness version: compare each claim with the record valid at this shot."""
    if shot in world.ALLOWED:
        return [Finding(c, "OK", f"意図的な不連続（{world.ALLOWED[shot]}）") for c in extract(text)]
    out = []
    for c in extract(text):
        rec = world.expected(db, c.entity, c.attr, shot, toward=c.toward)
        if rec is None:
            out.append(Finding(c, "不明", "記録なし（推測で埋めない）"))
        elif rec["value"] == c.value:
            out.append(Finding(c, "OK", f"記録どおり（{rec['cause']}）"))
        else:
            out.append(Finding(c, "矛盾", f"記録は「{rec['value']}」（{rec['cause']}、S{rec['since']}から）"))
    return out


def check_without_memory(shot: int, text: str) -> list[Finding]:
    """Baseline: sees only the previous shot's text, knows no events."""
    prev = {(c.entity, c.attr, c.toward): c.value for c in extract(world.SHOTS.get(shot - 1, ""))}
    out = []
    for c in extract(text):
        before = prev.get((c.entity, c.attr, c.toward))
        if before is None:
            out.append(Finding(c, "不明", "直前のショットに記述なし"))
        elif before == c.value:
            out.append(Finding(c, "OK", "直前のショットと同じ"))
        else:
            out.append(Finding(c, "矛盾", f"直前のショットでは「{before}」"))
    return out


# (shot, text, has_contradiction)
CASES = [
    (4, "ミナが剣を右手で振る。", True),
    (7, "カイが鍵を取り出して廊下へ向かう。", True),
    (7, "カイが走って部室を出ていく。", True),
    (7, "開いたドアの向こうに廊下が見える。", True),
    (2, "昼の光が差し込む部室。", True),
    (7, "ミナが画面右、カイが画面左で向き合う。", True),
    (7, "机の右にノートPCが置かれている。", True),
    (6, "上着なしのカイが割れたグラスを見下ろす。", False),
    (5, "ミナが鍵をポケットにしまう。", False),
    (4, "半分残ったコーヒーの横で、眼鏡のカイが顔をしかめる。", False),
    # extra cases in the current world (plan step 2)
    (7, "眼鏡を外したカイがノートを読む。", True),
    (7, "無傷のグラスが机に置かれている。", True),
    (5, "足を引きずるカイが窓を見る。", False),
    (7, "ミナが鍵をドアに差し込む。", False),
    # relationship cases (ミナ→カイ 信頼 since S4)
    (7, "ミナがカイを警戒して距離をとる。", True),
    (5, "カイを信じるミナが鍵を握る。", False),
]


def evaluate(db):
    rows, score = [], {"graph": [0, 0], "base": [0, 0]}  # [found, false positives]
    for shot, text, bad in CASES:
        g = any(f.status == "矛盾" for f in check_with_graph(db, shot, text))
        b = any(f.status == "矛盾" for f in check_without_memory(shot, text))
        for key, hit in (("graph", g), ("base", b)):
            if bad and hit:
                score[key][0] += 1
            if not bad and hit:
                score[key][1] += 1
        rows.append((shot, text, "矛盾あり" if bad else "矛盾なし", b, g))
    n_bad = sum(1 for c in CASES if c[2])
    n_ok = len(CASES) - n_bad
    return rows, score, n_bad, n_ok


if __name__ == "__main__":
    db = world.build()
    rows, score, n_bad, n_ok = evaluate(db)
    for shot, text, truth, b, g in rows:
        print(f"S{shot} {truth:4} 記憶なし={'赤' if b else '-'} グラフ={'赤' if g else '-'}  {text}")
    print(f"記憶なし: 発見 {score['base'][0]}/{n_bad}  誤検出 {score['base'][1]}/{n_ok}")
    print(f"グラフ  : 発見 {score['graph'][0]}/{n_bad}  誤検出 {score['graph'][1]}/{n_ok}")
