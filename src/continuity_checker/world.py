"""Sample world (original) and its continuity record, loaded into Relate.

Every state is stored as an interval: valid from shot `from` to shot `to`.
A change (taking off a jacket, handing over a key) closes one interval and
opens the next, and records its cause, so a legitimate change is never red.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import relate

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "continuity.rl"
END = 99

# The shot list as written (the "source of truth" the record was built from).
SHOTS = {
    1: "夜・雨。部室。赤い上着でポニーテールのミナが剣を右手に持ち、画面左に立つ。青い上着で眼鏡のカイは画面右。机の左にノートPC、満杯のコーヒー、スマホ。",
    2: "ミナが部室のドアを閉める。",
    3: "ミナが剣を左手に持ち替える。カイがコーヒーを半分飲む。",
    4: "カイが机の脚につまずき、左足をケガする。カイがミナに鍵を渡す。",
    5: "雨上がり。カイが青い上着を脱ぐ。",
    6: "カイがグラスを落とし、グラスが割れる。",
}

ENTITIES = [
    ("Character", "ミナ"),
    ("Character", "カイ"),
    ("Object", "剣"),
    ("Object", "鍵"),
    ("Object", "ノートPC"),
    ("Object", "コーヒー"),
    ("Object", "グラス"),
    ("Place", "部室"),
]

# (entity, attr, value, from, to, cause)
STATES = [
    # A. state carry-over
    ("ミナ", "上着", "赤", 1, END, "S1 設定"),
    ("ミナ", "髪型", "ポニーテール", 1, END, "S1 設定"),
    ("カイ", "上着", "青", 1, 4, "S1 設定"),
    ("カイ", "上着", "なし", 5, END, "S5 上着を脱ぐ"),
    ("カイ", "眼鏡", "あり", 1, END, "S1 設定"),
    ("カイ", "左足", "ケガ", 4, END, "S4 つまずいてケガ"),
    ("コーヒー", "量", "満杯", 1, 2, "S1 設定"),
    ("コーヒー", "量", "半分", 3, END, "S3 半分飲む"),
    ("グラス", "状態", "無事", 1, 5, "S1 設定"),
    ("グラス", "状態", "割れた", 6, END, "S6 割れる"),
    ("部室", "ドア", "閉", 2, END, "S2 ミナが閉める"),
    ("部室", "時間帯", "夜", 1, END, "S1 設定"),
    ("部室", "天気", "雨", 1, 4, "S1 設定"),
    ("部室", "天気", "雨上がり", 5, END, "S5 雨上がり"),
    # B. holding and handing over
    ("剣", "持ち手", "右手", 1, 2, "S1 設定"),
    ("剣", "持ち手", "左手", 3, END, "S3 持ち替え"),
    ("鍵", "持ち主", "カイ", 1, 3, "S1 設定"),
    ("鍵", "持ち主", "ミナ", 4, END, "S4 カイがミナに渡す"),
    # C. spatial placement
    ("ミナ", "立ち位置", "画面左", 1, END, "S1 設定"),
    ("カイ", "立ち位置", "画面右", 1, END, "S1 設定"),
    ("ノートPC", "位置", "机の左", 1, END, "S1 設定"),
    # D. fixed traits
    ("ミナ", "利き手", "右", 1, END, "キャラ設定"),
]

# Shots whose discontinuity is intended (flashback, dream). Never red.
ALLOWED = {}  # e.g. {9: "回想"}


def build(path: Path = DB_PATH):
    """Rebuild the store from the data above and return an open connection."""
    if path.exists():
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    db = relate.connect(str(path))
    for label, name in ENTITIES:
        db.execute(f"CREATE (:{label}:Entity {{name: $name}})", {"name": name})
    for ent, attr, value, start, end, cause in STATES:
        db.execute(
            "MATCH (e:Entity {name: $ent}) "
            "CREATE (e)-[:STATE {attr: $attr, value: $value, from: $from, to: $to, cause: $cause}]->(e)",
            {"ent": ent, "attr": attr, "value": value, "from": start, "to": end, "cause": cause},
        )
    for no, text in SHOTS.items():
        db.execute("CREATE (:Shot {no: $no, text: $text})", {"no": no, "text": text})
    db.execute("MATCH (a:Shot), (b:Shot) WHERE b.no = a.no + 1 CREATE (a)-[:NEXT]->(b)")
    return db


def expected(db, entity: str, attr: str, shot: int):
    """The recorded value of (entity, attr) at a shot, or None when unknown."""
    rows = list(db.execute(
        "MATCH (e:Entity {name: $ent})-[s:STATE]->(e) "
        "WHERE s.attr = $attr AND s.from <= $shot AND s.to >= $shot "
        "RETURN s.value AS value, s.cause AS cause, s.from AS since",
        {"ent": entity, "attr": attr, "shot": shot},
    ))
    return rows[0] if rows else None


if __name__ == "__main__":
    db = build()
    print(list(db.execute("MATCH (e:Entity) RETURN count(e) AS entities")))
    print(list(db.execute("MATCH ()-[s:STATE]->() RETURN count(s) AS states")))
    print(expected(db, "剣", "持ち手", 7))
